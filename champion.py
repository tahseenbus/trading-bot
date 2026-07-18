"""Champion / Challenger: run ALL strategies as parallel paper portfolios.

Every strategy gets its own $10,000 of fake money and trades live at the
same time. After a few weeks, reality -- not a backtest -- tells you which
strategy actually earns. This is the honest way to choose a champion.

Runs one market check per invocation and saves every portfolio to
portfolios.json, so it fits the same hourly GitHub Actions schedule as
paper_trade.py. Trades are logged to champion_trades.csv.

Run:            python champion.py
Hourly candles: python champion.py --timeframe 1h
Test one loop:  python champion.py --iterations 1
Stop:           Ctrl+C
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

PORTFOLIOS_FILE = Path(__file__).parent / "portfolios.json"
TRADES_FILE = Path(__file__).parent / "champion_trades.csv"
CANDLES_NEEDED = 250


def fresh_portfolio() -> dict:
    """A brand-new $START_CASH portfolio with no open position."""
    return {
        "cash": float(config.START_CASH), "btc": 0.0,
        "stop": 0.0, "target": 0.0, "entry": 0.0,
        "start_cash": float(config.START_CASH),
        "cooldown": 0, "trades": 0, "wins": 0,
    }


def load_portfolios() -> dict:
    """One portfolio per strategy, restored from disk or freshly created."""
    saved = {}
    if PORTFOLIOS_FILE.exists():
        try:
            saved = json.loads(PORTFOLIOS_FILE.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            print("[portfolios.json unreadable -- starting all fresh]")
    # Ensure every current strategy has a portfolio (new strategies join
    # with a fresh balance; removed ones simply drop out).
    return {name: saved.get(name, fresh_portfolio()) for name in STRATEGIES}


def save_portfolios(portfolios: dict) -> None:
    PORTFOLIOS_FILE.write_text(json.dumps(portfolios, indent=2))


def log_trade(strategy: str, side: str, price: float, value: float,
              start_cash: float) -> None:
    is_new = not TRADES_FILE.exists()
    with open(TRADES_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["time", "strategy", "side", "price",
                             "portfolio_value", "profit_loss"])
        writer.writerow([datetime.now().isoformat(timespec="seconds"),
                         strategy, side, f"{price:.2f}", f"{value:.2f}",
                         f"{value - start_cash:+.2f}"])


def step(strategy: str, p: dict, last, price: float,
         trend_ok: bool = True) -> str | None:
    """Advance one portfolio by one candle. Mirrors the live rules in
    paper_trade.py (stop/target/trailing, cooldown, circuit breaker,
    maker/taker fees, daily trend filter).
    Returns a short event string if a trade happened, else None."""
    atr = last["atr"]
    if p["btc"] > 0:
        if price <= p["stop"]:
            fill, fee = exit_fill(price, is_stop=True)
            was_loss = price < p["entry"]
            p["cash"] += p["btc"] * fill * (1 - fee)
            p["btc"] = 0.0
            p["trades"] += 1
            if not was_loss:
                p["wins"] += 1
            else:
                p["cooldown"] = config.COOLDOWN_CANDLES
            log_trade(strategy, "SELL (stop)", price, p["cash"], p["start_cash"])
            return f"STOP  ${price:,.0f}"
        if not config.TRAILING_STOP and price >= p["target"]:
            fill, fee = exit_fill(price, is_stop=False)
            p["cash"] += p["btc"] * fill * (1 - fee)
            p["btc"] = 0.0
            p["trades"] += 1
            p["wins"] += 1
            log_trade(strategy, "SELL (target)", price, p["cash"], p["start_cash"])
            return f"TAKE  ${price:,.0f}"
        if config.TRAILING_STOP and atr > 0:
            p["stop"] = max(p["stop"], price - config.STOP_ATR_MULT * atr)
        return None

    # Not in a position.
    value = p["cash"]
    if value < p["start_cash"] * (1 - config.MAX_ACCOUNT_LOSS):
        return None  # circuit breaker: no new trades
    if p["cooldown"] > 0:
        p["cooldown"] -= 1
        return None
    if last["entry_signal"] and atr > 0 and trend_ok:
        entry, fee = entry_fill(price)
        stop, target = stop_and_target(entry, atr)
        qty = position_size(p["cash"], entry, stop)
        spend = qty * entry * (1 + fee)
        if spend <= p["cash"] and qty > 0:
            p["btc"] = qty
            p["cash"] -= spend
            p["stop"], p["target"], p["entry"] = stop, target, entry
            log_trade(strategy, "BUY", entry, p["cash"] + qty * price, p["start_cash"])
            return f"BUY   ${entry:,.0f}"
    return None


def leaderboard(portfolios: dict, price: float) -> None:
    rows = []
    for name, p in portfolios.items():
        value = p["cash"] + p["btc"] * price
        pnl = value - p["start_cash"]
        wr = p["wins"] / p["trades"] if p["trades"] else 0.0
        rows.append((value, name, pnl, p["trades"], wr, p["btc"] > 0))
    rows.sort(reverse=True)

    print(f"\n{'#':>2} {'strategy':22} {'value':>11} {'earned/lost':>13} "
          f"{'trades':>6} {'win%':>5} {'holding':>7}")
    print("-" * 72)
    for i, (value, name, pnl, trades, wr, holding) in enumerate(rows, 1):
        pnl_str = f"{'+' if pnl >= 0 else '-'}${abs(pnl):,.2f}"
        print(f"{i:>2} {name:22} ${value:>10,.2f} {pnl_str:>13} "
              f"{trades:>6} {wr:>4.0%} {'yes' if holding else '':>7}")


def run(max_iterations: int | None = None) -> None:
    portfolios = load_portfolios()
    print(f"Champion/Challenger: all {len(STRATEGIES)} strategies | "
          f"{config.SYMBOL} on {config.PAPER_TIMEFRAME} candles")
    print(f"Each starts with ${config.START_CASH:,.2f} FAKE money. Ctrl+C to stop.")

    iteration = 0
    while True:
        try:
            candles = fetch_candles(config.PAPER_TIMEFRAME, limit=CANDLES_NEEDED,
                                    use_cache=False)
            price = candles["close"].iloc[-1]
            now = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
            trend_ok = trend_allows_entry()  # one daily-trend check for all
            events = []
            for name in STRATEGIES:
                df = add_indicators(candles, name)
                event = step(name, portfolios[name], df.iloc[-1], price, trend_ok)
                if event:
                    events.append(f"{name}: {event}")
            save_portfolios(portfolios)

            print(f"\n[{now}] BTC ${price:,.2f}")
            if events:
                print("  TRADES: " + " | ".join(events))
            leaderboard(portfolios, price)
        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}] error: {e} (retrying)")

        iteration += 1
        if max_iterations is not None and iteration >= max_iterations:
            break
        time.sleep(config.POLL_SECONDS)


if __name__ == "__main__":
    args = sys.argv
    iterations = int(args[args.index("--iterations") + 1]) if "--iterations" in args else None
    if "--symbol" in args:
        config.SYMBOL = args[args.index("--symbol") + 1].upper()
    if "--timeframe" in args:
        config.PAPER_TIMEFRAME = args[args.index("--timeframe") + 1]
    try:
        run(iterations)
    except KeyboardInterrupt:
        print("\nStopped.")
