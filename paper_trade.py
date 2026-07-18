"""Paper trader: runs the strategy on LIVE market data with FAKE money.

No account, no API keys, no real funds — it just watches real prices
and pretends to trade. Every position has a stop-loss and a take-profit
at 2:1 reward/risk, and risks only 2% of the account.

Run:             python paper_trade.py
Pick a strategy: python paper_trade.py --strategy rsi_reversion
Stop:            Ctrl+C
Test one loop:   python paper_trade.py --iterations 1
"""

import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import config
from data import fetch_candles
from strategies import (STRATEGIES, add_indicators, entry_fill, exit_fill,
                        position_size, stop_and_target, trend_allows_entry)

TRADES_FILE = Path(__file__).parent / "trades.csv"
STATE_FILE = Path(__file__).parent / "state.json"

# Enough candles for the slowest indicator any strategy uses, plus headroom.
CANDLES_NEEDED = 250


def log_trade(side: str, price: float, portfolio_value: float,
              start_cash: float) -> None:
    is_new = not TRADES_FILE.exists()
    profit_loss = portfolio_value - start_cash
    with open(TRADES_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["time", "side", "price", "portfolio_value",
                             "initial_investment", "profit_loss"])
        writer.writerow([datetime.now().isoformat(timespec="seconds"),
                         side, f"{price:.2f}", f"{portfolio_value:.2f}",
                         f"{start_cash:.2f}", f"{profit_loss:+.2f}"])


def save_state(strategy, cash, btc, stop, target, entry, start_cash):
    """Remember the portfolio between restarts (it's only fake money,
    but losing track of an open position would still be confusing)."""
    STATE_FILE.write_text(json.dumps({
        "symbol": config.SYMBOL, "strategy": strategy, "cash": cash,
        "btc": btc, "stop": stop, "target": target, "entry": entry,
        "start_cash": start_cash,
    }))


def load_state(strategy):
    """Restore a previous session if it was for the same coin + strategy."""
    if not STATE_FILE.exists():
        return None
    try:
        # utf-8-sig also tolerates files saved with a Windows BOM
        state = json.loads(STATE_FILE.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        print("[state.json was unreadable -- starting fresh]")
        return None
    if state.get("symbol") == config.SYMBOL and state.get("strategy") == strategy:
        return state
    return None


def run(max_iterations: int | None = None, strategy: str | None = None) -> None:
    strategy = strategy or config.STRATEGY
    if strategy not in STRATEGIES:
        raise SystemExit(f"Unknown strategy '{strategy}'. Options: {', '.join(STRATEGIES)}")

    cash = float(config.START_CASH)
    start_cash = float(config.START_CASH)   # the initial investment
    btc = 0.0
    stop = target = entry = 0.0
    previous = load_state(strategy)
    if previous:
        cash, btc = previous["cash"], previous["btc"]
        stop, target, entry = previous["stop"], previous["target"], previous["entry"]
        start_cash = previous.get("start_cash", start_cash)
        print(f"[resumed previous session: ${cash:,.2f} cash, {btc:.6f} BTC"
              + (f", open position from ${entry:,.2f}" if btc > 0 else "")
              + " -- delete state.json to start fresh]")

    def pnl_str(value: float) -> str:
        """'+$123.45 (+1.2%)' earned/lost versus the initial investment."""
        pnl = value - start_cash
        return f"{'+' if pnl >= 0 else '-'}${abs(pnl):,.2f} ({pnl / start_cash:+.1%})"

    cooldown = 0   # polls left before we may buy again after a losing trade

    print(f"Paper trading {config.SYMBOL} on {config.PAPER_TIMEFRAME} candles")
    print(f"Strategy: {strategy} -- {STRATEGIES[strategy][1]}")
    print(f"Settings: {config.STRATEGY_SETTINGS[strategy]} | stop {config.STOP_ATR_MULT}xATR, "
          f"target {config.REWARD_RISK}:1, risking {config.RISK_PER_TRADE:.0%} per trade")
    print(f"Initial investment: ${start_cash:,.2f} of FAKE money. Press Ctrl+C to stop.\n")

    iteration = 0
    while True:
        try:
            # use_cache=False: live trading always wants the newest prices
            candles = fetch_candles(config.PAPER_TIMEFRAME, limit=CANDLES_NEEDED,
                                    use_cache=False)
            df = add_indicators(candles, strategy)
            last = df.iloc[-1]
            price = last["close"]
            now = f"{datetime.now():%H:%M:%S}"

            if btc > 0:
                value = cash + btc * price
                if price <= stop:
                    # Stop-loss = market (taker) order with slippage.
                    sell_fill, fee = exit_fill(price, is_stop=True)
                    was_loss = price < entry
                    cash += btc * sell_fill * (1 - fee)
                    print(f"[{now}] STOP-LOSS hit at ${price:,.2f} "
                          f"(entered ${entry:,.2f}) -> ${cash:,.2f} cash | "
                          f"total: {pnl_str(cash)}")
                    log_trade("SELL (stop-loss)", price, cash, start_cash)
                    btc = 0.0
                    if was_loss:
                        cooldown = config.COOLDOWN_CANDLES
                    save_state(strategy, cash, btc, stop, target, entry, start_cash)
                elif not config.TRAILING_STOP and price >= target:
                    # Take-profit rests as a cheaper maker limit order.
                    sell_fill, fee = exit_fill(price, is_stop=False)
                    cash += btc * sell_fill * (1 - fee)
                    print(f"[{now}] TAKE-PROFIT hit at ${price:,.2f} "
                          f"(entered ${entry:,.2f}) -> ${cash:,.2f} cash | "
                          f"total: {pnl_str(cash)}")
                    log_trade("SELL (take-profit)", price, cash, start_cash)
                    btc = 0.0
                    save_state(strategy, cash, btc, stop, target, entry, start_cash)
                else:
                    if config.TRAILING_STOP and last["atr"] > 0:
                        # Ratchet the stop up as price rises; never lower it.
                        new_stop = max(stop, price - config.STOP_ATR_MULT * last["atr"])
                        if new_stop != stop:
                            stop = new_stop
                            save_state(strategy, cash, btc, stop, target, entry, start_cash)
                    print(f"[{now}] holding {btc:.6f} BTC | ${price:,.2f} | "
                          f"stop ${stop:,.2f} / target ${target:,.2f} | "
                          f"portfolio ${value:,.2f} | {pnl_str(value)}")
            elif cash < start_cash * (1 - config.MAX_ACCOUNT_LOSS):
                print(f"[{now}] CIRCUIT BREAKER: down more than "
                      f"{config.MAX_ACCOUNT_LOSS:.0%} from the initial "
                      f"investment -- not opening new trades | {pnl_str(cash)}")
            elif cooldown > 0:
                cooldown -= 1
                print(f"[{now}] cooldown after a loss ({cooldown} checks left) | "
                      f"BTC ${price:,.2f} | cash ${cash:,.2f}")
            elif last["entry_signal"] and last["atr"] > 0 and not trend_allows_entry():
                print(f"[{now}] {strategy} signal, but the daily trend is DOWN "
                      f"(price under its {config.TREND_FILTER_SMA}-day average) "
                      f"-- skipping | BTC ${price:,.2f}")
            elif last["entry_signal"] and last["atr"] > 0:
                entry, fee = entry_fill(price)
                stop, target = stop_and_target(entry, last["atr"])
                qty = position_size(cash, entry, stop)
                spend = qty * entry * (1 + fee)
                if spend <= cash and qty > 0:
                    btc = qty
                    cash -= spend
                    print(f"[{now}] BUY ({strategy}) {qty:.6f} BTC at ${entry:,.2f} | "
                          f"stop ${stop:,.2f} / target ${target:,.2f}")
                    log_trade(f"BUY ({strategy})", entry, cash + btc * price, start_cash)
                    save_state(strategy, cash, btc, stop, target, entry, start_cash)
                else:
                    print(f"[{now}] entry signal but can't size the trade "
                          f"(cash ${cash:,.2f}) -- skipped")
            else:
                print(f"[{now}] waiting for {strategy} signal | "
                      f"BTC ${price:,.2f} | cash ${cash:,.2f} | {pnl_str(cash)}")
        except Exception as e:  # network hiccups shouldn't kill the bot
            print(f"[{datetime.now():%H:%M:%S}] error: {e} (retrying)")

        # Persist the portfolio every check (anchors start_cash on the
        # first run and lets scheduled/hosted runs resume from here).
        save_state(strategy, cash, btc, stop, target, entry, start_cash)

        iteration += 1
        if max_iterations is not None and iteration >= max_iterations:
            break
        time.sleep(config.POLL_SECONDS)


if __name__ == "__main__":
    args = sys.argv
    iterations = int(args[args.index("--iterations") + 1]) if "--iterations" in args else None
    strategy = args[args.index("--strategy") + 1] if "--strategy" in args else None
    if "--symbol" in args:  # e.g. --symbol ETH/USD
        config.SYMBOL = args[args.index("--symbol") + 1].upper()
    if "--timeframe" in args:  # e.g. --timeframe 5m (signals form on 5m candles)
        config.PAPER_TIMEFRAME = args[args.index("--timeframe") + 1]
    try:
        run(iterations, strategy)
    except KeyboardInterrupt:
        print("\nStopped.")
