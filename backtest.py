"""Backtester: replays a strategy over historical data to see how it
WOULD have done. Includes trading fees.

Run:                  python backtest.py                (random slice, config strategy)
Pick a strategy:      python backtest.py --strategy macd
List strategies:      python backtest.py --list
Race all strategies:  python backtest.py --compare      (same data for all 10)
Reproduce a run:      python backtest.py --seed 42
Use full history:     edit RANDOM_WINDOW = False in config.py

Exit rules inside each candle: if both the stop and the target were
touched in the same candle, we assume the stop hit first (the
pessimistic assumption — better to underestimate results than inflate
them).
"""

import random
import sys

import config
from data import fetch_candles
from strategies import STRATEGIES, add_indicators, position_size, stop_and_target


def pick_window(candles, rng):
    """Return a random contiguous slice of the candles DataFrame.

    Each run tests a different date range, so you see how the strategy
    behaves across many market conditions instead of always the same one.
    """
    n = len(candles)
    max_window = min(config.MAX_WINDOW, n)
    min_window = min(config.MIN_WINDOW, max_window)
    window = rng.randint(min_window, max_window)
    start = rng.randint(0, n - window)
    return candles.iloc[start:start + window]


def simulate(df):
    """Run the trade simulation over signal-annotated candles.

    Returns a stats dict; shared by the single-strategy report and
    the --compare table.
    """
    start_cash = float(config.START_CASH)
    cash = start_cash
    btc = 0.0
    stop = target = entry = 0.0
    trades = []          # (time, result, entry, exit, profit_dollars)
    peak = start_cash    # highest portfolio value seen so far
    max_drawdown = 0.0   # worst peak-to-valley drop, as a fraction
    cooldown = 0         # candles left before we may buy again after a loss
    halted = False       # circuit breaker: too much lost, no new positions

    for time, row in df.iterrows():
        if btc > 0:
            # In a position: check stop first (pessimistic), then target.
            exit_price = None
            if row["low"] <= stop:
                exit_price = stop
                result = "WIN  (trail)" if stop > entry else "LOSS (stop)"
            elif not config.TRAILING_STOP and row["high"] >= target:
                exit_price, result = target, "WIN  (target)"
            elif config.TRAILING_STOP and row["atr"] > 0:
                # Ratchet the stop up as price rises; never lower it.
                stop = max(stop, row["close"] - config.STOP_ATR_MULT * row["atr"])
            if exit_price is not None:
                # Sells fill slightly below the trigger price (slippage).
                fill = exit_price * (1 - config.SLIPPAGE)
                proceeds = btc * fill * (1 - config.FEE_RATE)
                cost = btc * entry * (1 + config.FEE_RATE)
                pnl = proceeds - cost
                trades.append((time, result, entry, exit_price, pnl))
                cash += proceeds
                btc = 0.0
                if pnl < 0:
                    # Don't instantly re-buy the same falling market.
                    cooldown = config.COOLDOWN_CANDLES
        elif cooldown > 0:
            cooldown -= 1
        elif halted:
            pass  # circuit breaker tripped: sit out the rest of the test
        elif row["entry_signal"] and row["atr"] > 0:
            # Buys fill slightly above the printed price (slippage).
            entry = row["close"] * (1 + config.SLIPPAGE)
            stop, target = stop_and_target(entry, row["atr"])
            qty = position_size(cash, entry, stop)
            spend = qty * entry * (1 + config.FEE_RATE)
            if spend <= cash:
                btc = qty
                cash -= spend

        # Track the equity curve to measure drawdown (worst losing streak).
        value = cash + btc * row["close"]
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, 1 - value / peak)
        if value < start_cash * (1 - config.MAX_ACCOUNT_LOSS):
            halted = True

    final_value = cash + btc * df["close"].iloc[-1]
    wins = [t for t in trades if t[4] > 0]
    losses = [t for t in trades if t[4] <= 0]
    gross_profit = sum(t[4] for t in wins)
    gross_loss = -sum(t[4] for t in losses)
    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "final_value": final_value,
        "pnl": final_value - start_cash,
        "return": final_value / start_cash - 1,
        "halted": halted,
        "max_drawdown": max_drawdown,
        # Profit factor: dollars won per dollar lost. Above 1.0 = profitable.
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        # Expectancy: average dollars made (or lost) per trade.
        "expectancy": sum(t[4] for t in trades) / len(trades) if trades else 0.0,
    }


def get_candles(seed):
    """Fetch history and (by default) cut a random window from it."""
    candles = fetch_candles(config.BACKTEST_TIMEFRAME)
    if config.RANDOM_WINDOW:
        # If no seed given, pick a random one and print it so any
        # interesting run can be reproduced later with --seed.
        if seed is None:
            seed = random.randrange(1_000_000)
        rng = random.Random(seed)
        candles = pick_window(candles, rng)
        print(f"[random window, seed {seed} -- rerun with: python backtest.py --seed {seed}]")
    return candles


def run_many(n, strategy=None, seed=None):
    """Monte Carlo test: run the strategy over n random windows and show
    the DISTRIBUTION of outcomes. One backtest can get lucky; a hundred
    windows tell you how the strategy behaves across market conditions."""
    strategy = strategy or config.STRATEGY
    all_candles = fetch_candles(config.BACKTEST_TIMEFRAME)
    rng = random.Random(seed)

    returns, trade_counts, beat_hold = [], [], 0
    for _ in range(n):
        window = pick_window(all_candles, rng)
        stats = simulate(add_indicators(window, strategy))
        returns.append(stats["return"])
        trade_counts.append(len(stats["trades"]))
        hold = window["close"].iloc[-1] / window["close"].iloc[0] - 1
        if stats["return"] > hold:
            beat_hold += 1

    returns.sort()
    median = returns[len(returns) // 2]
    profitable = sum(1 for r in returns if r > 0)
    def dollars(r):
        pnl = config.START_CASH * r
        return f"{'+' if pnl >= 0 else '-'}${abs(pnl):,.0f}"

    print(f"Monte Carlo: {strategy} | {n} random windows of "
          f"{config.MIN_WINDOW}-{config.MAX_WINDOW} candles | {config.SYMBOL}")
    print(f"Initial investment: ${config.START_CASH:,.2f} per window")
    print("-" * 60)
    print(f"Median outcome:       {dollars(median):>10}  ({median:+.1%})")
    avg = sum(returns) / n
    print(f"Average outcome:      {dollars(avg):>10}  ({avg:+.1%})")
    print(f"Best window:          {dollars(returns[-1]):>10}  ({returns[-1]:+.1%})")
    print(f"Worst window:         {dollars(returns[0]):>10}  ({returns[0]:+.1%})")
    print(f"Profitable windows:   {profitable}/{n}  ({profitable / n:.0%})")
    print(f"Beat buy & hold:      {beat_hold}/{n}  ({beat_hold / n:.0%})")
    print(f"Avg trades per window:{sum(trade_counts) / n:>8.1f}")


def run_backtest(seed=None, strategy=None):
    strategy = strategy or config.STRATEGY
    candles = get_candles(seed)
    df = add_indicators(candles, strategy)
    stats = simulate(df)

    trades, wins, losses = stats["trades"], stats["wins"], stats["losses"]
    buy_and_hold = df["close"].iloc[-1] / df["close"].iloc[0] - 1
    avg_win = sum(t[4] for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(t[4] for t in losses) / len(losses) if losses else 0.0

    days = (df.index[-1] - df.index[0]).days
    print(f"Backtest: {config.SYMBOL} | {config.BACKTEST_TIMEFRAME} candles | "
          f"{df.index[0].date()} to {df.index[-1].date()} ({days} days)")
    print(f"Strategy: {strategy} -- {STRATEGIES[strategy][1]}")
    print(f"Settings: {config.STRATEGY_SETTINGS[strategy]} | stop {config.STOP_ATR_MULT}xATR, "
          f"target {config.REWARD_RISK}:1, risk {config.RISK_PER_TRADE:.0%}/trade")
    print("-" * 68)
    for time, result, entry_p, exit_p, pnl in trades[-10:]:
        print(f"{time.date()}  {result:14} in ${entry_p:>10,.0f}  out ${exit_p:>10,.0f}  "
              f"{'+' if pnl > 0 else ''}{pnl:,.2f}")
    if len(trades) > 10:
        print(f"(showing last 10 of {len(trades)} trades)")
    print("-" * 68)
    print(f"Trades: {len(trades)}  |  wins: {len(wins)}  losses: {len(losses)}"
          + (f"  |  win rate: {len(wins) / len(trades):.0%}" if trades else ""))
    if wins and losses:
        print(f"Average win:  +${avg_win:,.2f}")
        print(f"Average loss: -${-avg_loss:,.2f}   "
              f"(win/loss size ratio: {avg_win / -avg_loss:.2f} to 1)")
    if trades:
        pf = stats["profit_factor"]
        print(f"Profit factor:      {pf:>12.2f}  (dollars won per dollar lost)")
        print(f"Expectancy:         ${stats['expectancy']:>11,.2f}  per trade")
    print(f"Max drawdown:       {stats['max_drawdown']:>12.1%}  (worst drop from a peak)")
    if stats["halted"]:
        print(f"CIRCUIT BREAKER:    tripped at -{config.MAX_ACCOUNT_LOSS:.0%} "
              f"-- stopped opening new trades")
    pnl = stats["pnl"]
    hold_pnl = config.START_CASH * buy_and_hold
    print(f"Initial investment: ${config.START_CASH:>12,.2f}")
    print(f"Final value:        ${stats['final_value']:>12,.2f}")
    print(f"You {'EARNED' if pnl >= 0 else 'LOST':6}         {'+' if pnl >= 0 else '-'}"
          f"${abs(pnl):>11,.2f}  ({stats['return']:+.1%})")
    print(f"Buy & hold instead: {'+' if hold_pnl >= 0 else '-'}${abs(hold_pnl):>11,.2f}"
          f"  ({buy_and_hold:+.1%})")


def run_compare(seed=None):
    """Race all strategies over the SAME data window, best return first."""
    candles = get_candles(seed)
    days = (candles.index[-1] - candles.index[0]).days
    buy_and_hold = candles["close"].iloc[-1] / candles["close"].iloc[0] - 1

    print(f"Comparing all strategies: {config.SYMBOL} | "
          f"{candles.index[0].date()} to {candles.index[-1].date()} ({days} days)")
    print(f"Initial investment: ${config.START_CASH:,.2f}")
    print(f"{'strategy':22} {'trades':>6} {'wins':>5} {'losses':>6} "
          f"{'win rate':>8} {'earned/lost':>12} {'return':>8}")
    print("-" * 74)

    results = []
    for name in STRATEGIES:
        stats = simulate(add_indicators(candles, name))
        results.append((name, stats))
    results.sort(key=lambda r: r[1]["return"], reverse=True)

    for name, stats in results:
        n = len(stats["trades"])
        win_rate = f"{len(stats['wins']) / n:.0%}" if n else "-"
        pnl = stats["pnl"]
        pnl_str = f"{'+' if pnl >= 0 else '-'}${abs(pnl):,.0f}"
        print(f"{name:22} {n:>6} {len(stats['wins']):>5} {len(stats['losses']):>6} "
              f"{win_rate:>8} {pnl_str:>12} {stats['return']:>8.1%}")
    print("-" * 74)
    hold_pnl = config.START_CASH * buy_and_hold
    hold_str = f"{'+' if hold_pnl >= 0 else '-'}${abs(hold_pnl):,.0f}"
    print(f"{'buy & hold':22} {'':>6} {'':>5} {'':>6} {'':>8} "
          f"{hold_str:>12} {buy_and_hold:>8.1%}")


def run_compare_many(n, seed=None):
    """Rank ALL strategies across the same n random windows each.
    Far more trustworthy than one window: shows median result and how
    OFTEN each strategy makes money, not who got lucky once."""
    all_candles = fetch_candles(config.BACKTEST_TIMEFRAME)
    rng = random.Random(seed)
    windows = [pick_window(all_candles, rng) for _ in range(n)]

    print(f"Comparing all strategies across {n} random windows | {config.SYMBOL}")
    print(f"Initial investment: ${config.START_CASH:,.2f} per window")
    print(f"{'strategy':22} {'median $':>10} {'median':>8} {'average':>8} {'worst':>8} "
          f"{'profitable':>11} {'trades/win.':>11}")
    print("-" * 84)

    results = []
    for name in STRATEGIES:
        returns, n_trades = [], 0
        for window in windows:
            stats = simulate(add_indicators(window, name))
            returns.append(stats["return"])
            n_trades += len(stats["trades"])
        returns.sort()
        results.append((name, {
            "median": returns[len(returns) // 2],
            "average": sum(returns) / n,
            "worst": returns[0],
            "profitable": sum(1 for r in returns if r > 0) / n,
            "trades": n_trades / n,
        }))
    results.sort(key=lambda r: r[1]["median"], reverse=True)

    def dollars(r):
        pnl = config.START_CASH * r
        return f"{'+' if pnl >= 0 else '-'}${abs(pnl):,.0f}"

    for name, s in results:
        print(f"{name:22} {dollars(s['median']):>10} {s['median']:>8.1%} "
              f"{s['average']:>8.1%} {s['worst']:>8.1%} "
              f"{s['profitable']:>11.0%} {s['trades']:>11.1f}")
    hold_returns = sorted(w["close"].iloc[-1] / w["close"].iloc[0] - 1 for w in windows)
    hold_median = hold_returns[len(hold_returns) // 2]
    print("-" * 84)
    print(f"{'buy & hold':22} {dollars(hold_median):>10} {hold_median:>8.1%} "
          f"{sum(hold_returns) / n:>8.1%} {hold_returns[0]:>8.1%}")


def run_tune(strategy=None, seed=7, n_windows=30):
    """Sweep each setting of the strategy one at a time and score every
    variant over the same random windows (median return). Shows which
    knobs matter. WARNING: tuning numbers to fit past data is overfitting
    -- treat the winners as hints, not truth."""
    strategy = strategy or config.STRATEGY
    base = dict(config.STRATEGY_SETTINGS[strategy])
    all_candles = fetch_candles(config.BACKTEST_TIMEFRAME)
    rng = random.Random(seed)
    windows = [pick_window(all_candles, rng) for _ in range(n_windows)]

    def score(settings):
        config.STRATEGY_SETTINGS[strategy] = settings
        returns = sorted(simulate(add_indicators(w, strategy))["return"]
                         for w in windows)
        return returns[len(returns) // 2]

    print(f"Tuning {strategy} | median return over {n_windows} fixed random windows")
    print(f"Current settings: {base}\n")

    best = dict(base)
    for param, value in base.items():
        # Try the current value scaled down and up.
        candidates = sorted({
            type(value)(round(value * f, 4)) for f in (0.5, 0.75, 1.0, 1.25, 1.5)
            if (value * f) >= (2 if isinstance(value, int) else 0.001)
        })
        scores = []
        for candidate in candidates:
            trial = dict(best)
            trial[param] = candidate
            scores.append((score(trial), candidate))
        scores.sort(reverse=True)
        best_score, best_value = scores[0]
        marker = " <- current" if best_value == base[param] else " <- better!"
        print(f"{param:15} tried {candidates}")
        print(f"{'':15} best: {best_value}  (median {best_score:+.1%}){marker}")
        best[param] = best_value

    config.STRATEGY_SETTINGS[strategy] = base  # leave config untouched
    print(f"\nBest found: {best}")
    print("To adopt these, edit STRATEGY_SETTINGS in config.py.")
    print("Remember: numbers tuned on the past may not fit the future (overfitting).")


def print_list():
    print("Available strategies (set STRATEGY in config.py, or use --strategy):\n")
    for name, (_, description) in STRATEGIES.items():
        marker = "*" if name == config.STRATEGY else " "
        print(f" {marker} {name:22} {description}")
    print("\n(* = current default; tune each in config.STRATEGY_SETTINGS)")


if __name__ == "__main__":
    args = sys.argv
    if "--list" in args:
        print_list()
        sys.exit(0)
    seed = int(args[args.index("--seed") + 1]) if "--seed" in args else None
    strategy = args[args.index("--strategy") + 1] if "--strategy" in args else None
    runs = int(args[args.index("--runs") + 1]) if "--runs" in args else None
    if "--symbol" in args:  # e.g. --symbol ETH/USD
        config.SYMBOL = args[args.index("--symbol") + 1].upper()
    if "--timeframe" in args:  # e.g. --timeframe 1h (1m 5m 15m 1h 4h 1d 1w)
        config.BACKTEST_TIMEFRAME = args[args.index("--timeframe") + 1]
    if "--tune" in args:
        run_tune(strategy)
    elif "--compare" in args and runs:
        run_compare_many(runs, seed)
    elif "--compare" in args:
        run_compare(seed)
    elif runs:
        run_many(runs, strategy, seed)
    else:
        run_backtest(seed, strategy)
