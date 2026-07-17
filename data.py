"""Fetches free price data from the exchange's public API (no account needed).

Downloaded candles are cached in the cache/ folder so repeated backtests
don't re-download the same history (and don't hammer the exchange's API).
Live paper trading always fetches fresh data.
"""

import time
from pathlib import Path

import ccxt
import pandas as pd

import config

CACHE_DIR = Path(__file__).parent / "cache"

# How long a cached download stays fresh, per timeframe (seconds).
# Daily candles barely change within 15 minutes; minute candles do.
CACHE_TTL = {"1d": 900, "4h": 900, "1h": 300, "15m": 120, "5m": 60, "1m": 30}


def get_exchange() -> ccxt.Exchange:
    return getattr(ccxt, config.EXCHANGE)()


def fetch_candles(timeframe: str, limit: int = 720,
                  use_cache: bool = True) -> pd.DataFrame:
    """Fetch recent OHLCV candles as a DataFrame indexed by time.

    Each candle has: open, high, low, close prices and volume.
    Kraken returns at most 720 candles per timeframe.
    """
    cache_file = CACHE_DIR / (
        f"{config.EXCHANGE}_{config.SYMBOL.replace('/', '-')}_{timeframe}_{limit}.csv")
    ttl = CACHE_TTL.get(timeframe, 300)

    if use_cache and cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < ttl:
            return pd.read_csv(cache_file, index_col="time", parse_dates=["time"])

    exchange = get_exchange()
    raw = exchange.fetch_ohlcv(config.SYMBOL, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    df = df.set_index("time")

    if use_cache:
        CACHE_DIR.mkdir(exist_ok=True)
        df.to_csv(cache_file)
    return df


if __name__ == "__main__":
    candles = fetch_candles(config.BACKTEST_TIMEFRAME)
    print(f"Fetched {len(candles)} {config.BACKTEST_TIMEFRAME} candles for {config.SYMBOL}")
    print(candles.tail())
