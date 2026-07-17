"""Show how your paper trading has gone so far:  python report.py

Reads trades.csv (every trade the paper trader made) and state.json
(current portfolio), fetches the live price, and prints a summary:
initial investment, current value, and earned/lost overall.
"""

import csv
import json
from pathlib import Path

import config
from data import fetch_candles

TRADES_FILE = Path(__file__).parent / "trades.csv"
STATE_FILE = Path(__file__).parent / "state.json"


def money(x: float) -> str:
    return f"{'+' if x >= 0 else '-'}${abs(x):,.2f}"


def main() -> None:
    if not TRADES_FILE.exists() and not STATE_FILE.exists():
        print("No trading history yet. Run:  python paper_trade.py")
        return

    rows = []
    if TRADES_FILE.exists():
        with open(TRADES_FILE, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))

    print(f"Paper trading report | {config.SYMBOL}")
    print("=" * 56)

    # ---- trade history ----
    buys = [r for r in rows if r["side"].startswith("BUY")]
    stops = [r for r in rows if "stop-loss" in r["side"]]
    takes = [r for r in rows if "take-profit" in r["side"]]
    if rows:
        start_cash = float(rows[0]["initial_investment"])
        first, last = rows[0]["time"], rows[-1]["time"]
        print(f"History: {len(buys)} buys, {len(takes)} take-profits, "
              f"{len(stops)} stop-losses")
        print(f"         from {first}  to  {last}")
    else:
        start_cash = float(config.START_CASH)
        print("History: no trades logged yet")

    # ---- current portfolio ----
    state = None
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            pass

    if state:
        start_cash = state.get("start_cash", start_cash)
        cash, btc = state["cash"], state["btc"]
        price = fetch_candles(config.PAPER_TIMEFRAME, limit=2,
                              use_cache=False)["close"].iloc[-1]
        value = cash + btc * price
        print("-" * 56)
        print(f"Strategy:           {state['strategy']}")
        if btc > 0:
            unrealized = (price - state["entry"]) * btc
            print(f"Open position:      {btc:.6f} BTC bought at "
                  f"${state['entry']:,.2f}")
            print(f"  now ${price:,.2f} -> unrealized {money(unrealized)}")
            print(f"  stop ${state['stop']:,.2f}"
                  + ("" if config.TRAILING_STOP
                     else f" / target ${state['target']:,.2f}"))
        else:
            print(f"Open position:      none (all cash)")
        print("-" * 56)
        print(f"Initial investment: ${start_cash:,.2f}")
        print(f"Current value:      ${value:,.2f}")
        pnl = value - start_cash
        print(f"You {'EARNED' if pnl >= 0 else 'LOST'}         "
              f"{money(pnl):>12}  ({pnl / start_cash:+.2%})")
    elif rows:
        value = float(rows[-1]["portfolio_value"])
        pnl = value - start_cash
        print("-" * 56)
        print(f"Initial investment: ${start_cash:,.2f}")
        print(f"Value at last trade:${value:,.2f}")
        print(f"You {'EARNED' if pnl >= 0 else 'LOST'}         "
              f"{money(pnl):>12}  ({pnl / start_cash:+.2%})")


if __name__ == "__main__":
    main()
