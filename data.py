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


def fetch_deep_history(timeframe: str = "1d") -> pd.DataFrame:
    """Fetch YEARS of candles by paging through a free exchange that
    allows it (Coinbase). Kraken only serves the last ~720 candles;
    this walks forward from config.HISTORY_START in 300-candle pages.

    More history = more market conditions tested = less overfitting.
    Cached for a day (only today's candle ever changes).
    """
    cache_file = CACHE_DIR / (
        f"deep_{config.HISTORY_EXCHANGE}_{config.SYMBOL.replace('/', '-')}_{timeframe}.csv")
    if cache_file.exists() and time.time() - cache_file.stat().st_mtime < 86_400:
        return pd.read_csv(cache_file, index_col="time", parse_dates=["time"])

    exchange = getattr(ccxt, config.HISTORY_EXCHANGE)({"enableRateLimit": True})
    since = exchange.parse8601(f"{config.HISTORY_START}T00:00:00Z")
    rows = []
    while True:
        batch = exchange.fetch_ohlcv(config.SYMBOL, timeframe, since=since, limit=300)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 2:
            break
        since = batch[-1][0] + 1          # continue after the last candle
        if len(rows) > 20_000:            # safety cap
            break

    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    df = df.drop_duplicates("time").set_index("time").sort_index()
    # Drop today's still-forming candle so results don't shift intraday.
    df = df.iloc[:-1]

    CACHE_DIR.mkdir(exist_ok=True)
    df.to_csv(cache_file)
    return df


def fetch_backtest_candles() -> pd.DataFrame:
    """What the backtester should test on: deep multi-year history for
    daily candles (if enabled), otherwise the recent Kraken data."""
    if config.DEEP_HISTORY and config.BACKTEST_TIMEFRAME == "1d":
        return fetch_deep_history("1d")
    return fetch_candles(config.BACKTEST_TIMEFRAME)


if __name__ == "__main__":
    candles = fetch_backtest_candles()
    print(f"Fetched {len(candles)} {config.BACKTEST_TIMEFRAME} candles for "
          f"{config.SYMBOL}: {candles.index[0].date()} to {candles.index[-1].date()}")
    print(candles.tail())
