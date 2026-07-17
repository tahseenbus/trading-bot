"""Ten classic trading strategies, all switchable from config.py.

Every strategy only decides WHEN TO BUY. Exits are always handled by the
shared loss management (see stop_and_target / position_size below):
stop-loss at STOP_ATR_MULT ATRs below entry, take-profit at REWARD_RISK
times the stop distance, risking RISK_PER_TRADE of the account per trade.
That keeps the "one win pays for ~two losses" rule no matter which
strategy generated the entry.

Each strategy's tuning numbers live in config.STRATEGY_SETTINGS.
"""

import pandas as pd

import config


# ---------------------------------------------------------------- helpers

def sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n).mean()


def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, period: int) -> pd.Series:
    """Relative Strength Index, 0-100. Low = oversold, high = overbought."""
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    return 100 - 100 / (1 + gain / loss)


def atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Average True Range: how much price typically moves per candle."""
    prev_close = df["close"].shift(1)
    true_range = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return true_range.rolling(period).mean()


def crossed_above(a: pd.Series, b: pd.Series) -> pd.Series:
    """True on the exact candle where line a crosses up through line b."""
    return (a > b) & (a.shift(1) <= b.shift(1))


def adx(df: pd.DataFrame, period: int) -> pd.Series:
    """Average Directional Index, 0-100: how STRONGLY price is trending
    (in either direction). Above ~25 = trending, below = ranging."""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr_smooth = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_smooth
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_smooth
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


# ------------------------------------------------------------- strategies
# Each function receives the candle DataFrame and its settings dict, and
# must set df["entry_signal"] (True = buy now, if not already in a trade).

def strat_breakout(df, p):
    """Turtle-style: buy a close above the last N candles' high, uptrend only."""
    df["breakout_level"] = df["high"].rolling(p["lookback"]).max().shift(1)
    df["entry_signal"] = (
        (df["close"] > df["breakout_level"]) &
        (df["close"] > sma(df["close"], p["trend_sma"]))
    )


def strat_sma_cross(df, p):
    """Classic golden-cross style: fast average crosses above slow average."""
    df["fast_ma"] = sma(df["close"], p["fast"])
    df["slow_ma"] = sma(df["close"], p["slow"])
    df["entry_signal"] = crossed_above(df["fast_ma"], df["slow_ma"])


def strat_ema_cross(df, p):
    """Like sma_cross but with exponential averages, which react faster."""
    df["fast_ma"] = ema(df["close"], p["fast"])
    df["slow_ma"] = ema(df["close"], p["slow"])
    df["entry_signal"] = crossed_above(df["fast_ma"], df["slow_ma"])


def strat_macd(df, p):
    """MACD: buy when the MACD line crosses above its signal line."""
    macd_line = ema(df["close"], p["fast"]) - ema(df["close"], p["slow"])
    signal_line = ema(macd_line, p["signal"])
    df["macd"], df["macd_signal"] = macd_line, signal_line
    df["entry_signal"] = crossed_above(macd_line, signal_line)


def strat_rsi_reversion(df, p):
    """Mean reversion: buy the dip when RSI is oversold, but only in an uptrend."""
    df["rsi"] = rsi(df["close"], p["period"])
    df["entry_signal"] = (
        (df["rsi"] < p["oversold"]) &
        (df["close"] > sma(df["close"], p["trend_sma"]))
    )


def strat_bollinger_reversion(df, p):
    """Mean reversion: buy when price drops below the lower Bollinger band."""
    mid = sma(df["close"], p["period"])
    std = df["close"].rolling(p["period"]).std()
    df["bb_lower"] = mid - p["num_std"] * std
    df["bb_upper"] = mid + p["num_std"] * std
    df["entry_signal"] = df["close"] < df["bb_lower"]


def strat_bollinger_breakout(df, p):
    """Volatility breakout: buy when price pushes above the upper Bollinger band."""
    mid = sma(df["close"], p["period"])
    std = df["close"].rolling(p["period"]).std()
    df["bb_upper"] = mid + p["num_std"] * std
    df["entry_signal"] = df["close"] > df["bb_upper"]


def strat_momentum(df, p):
    """Momentum: buy when price has risen more than min_change over the lookback."""
    df["momentum"] = df["close"] / df["close"].shift(p["lookback"]) - 1
    df["entry_signal"] = df["momentum"] > p["min_change"]


def strat_volume_breakout(df, p):
    """Breakout confirmed by a volume spike (move backed by real buying)."""
    df["breakout_level"] = df["high"].rolling(p["lookback"]).max().shift(1)
    avg_volume = df["volume"].rolling(p["lookback"]).mean().shift(1)
    df["entry_signal"] = (
        (df["close"] > df["breakout_level"]) &
        (df["volume"] > p["volume_mult"] * avg_volume)
    )


def strat_stochastic(df, p):
    """Stochastic oscillator: buy when %K crosses above %D in oversold territory."""
    low_min = df["low"].rolling(p["k_period"]).min()
    high_max = df["high"].rolling(p["k_period"]).max()
    df["stoch_k"] = 100 * (df["close"] - low_min) / (high_max - low_min)
    df["stoch_d"] = sma(df["stoch_k"], p["d_period"])
    df["entry_signal"] = (
        crossed_above(df["stoch_k"], df["stoch_d"]) &
        (df["stoch_k"] < p["oversold"])
    )


def strat_macd_rsi(df, p):
    """Combo: MACD momentum cross, but skip entries where RSI says the
    move is already overextended (a common cause of buying the top)."""
    macd_line = ema(df["close"], p["fast"]) - ema(df["close"], p["slow"])
    signal_line = ema(macd_line, p["signal"])
    df["rsi"] = rsi(df["close"], p["rsi_period"])
    df["entry_signal"] = (
        crossed_above(macd_line, signal_line) &
        (df["rsi"] < p["rsi_max"])
    )


def strat_regime_adaptive(df, p):
    """Meta-strategy: measure trend strength with ADX, then use the right
    tool for the regime -- breakouts when trending, dip-buying when ranging.
    (No single strategy wins in all conditions; this one switches.)"""
    df["adx"] = adx(df, p["adx_period"])
    trending = df["adx"] > p["adx_threshold"]

    # Trending regime: buy new highs (breakout logic).
    breakout_level = df["high"].rolling(p["lookback"]).max().shift(1)
    trend_entry = df["close"] > breakout_level

    # Ranging regime: buy oversold dips (RSI reversion logic).
    df["rsi"] = rsi(df["close"], p["rsi_period"])
    range_entry = df["rsi"] < p["oversold"]

    df["entry_signal"] = (trending & trend_entry) | (~trending & range_entry)


# name -> (function, one-line description shown by --list)
STRATEGIES = {
    "breakout":            (strat_breakout, "Buy new highs in an uptrend (Turtle style)"),
    "sma_cross":           (strat_sma_cross, "Fast SMA crosses above slow SMA"),
    "ema_cross":           (strat_ema_cross, "Fast EMA crosses above slow EMA (quicker)"),
    "macd":                (strat_macd, "MACD line crosses above its signal line"),
    "rsi_reversion":       (strat_rsi_reversion, "Buy oversold dips in an uptrend"),
    "bollinger_reversion": (strat_bollinger_reversion, "Buy below the lower Bollinger band"),
    "bollinger_breakout":  (strat_bollinger_breakout, "Buy above the upper Bollinger band"),
    "momentum":            (strat_momentum, "Buy when recent gains exceed a threshold"),
    "volume_breakout":     (strat_volume_breakout, "Breakout confirmed by a volume spike"),
    "stochastic":          (strat_stochastic, "Stochastic %K/%D cross while oversold"),
    "macd_rsi":            (strat_macd_rsi, "MACD cross, skipping overextended (high RSI) entries"),
    "regime_adaptive":     (strat_regime_adaptive, "ADX picks: breakouts in trends, dips in ranges"),
}


def add_indicators(candles: pd.DataFrame, name: str | None = None) -> pd.DataFrame:
    """Run the chosen strategy (default: config.STRATEGY) over the candles.

    Returns a copy with an "entry_signal" column plus "atr" for the stops.
    """
    name = name or config.STRATEGY
    if name not in STRATEGIES:
        options = ", ".join(STRATEGIES)
        raise ValueError(f"Unknown strategy '{name}'. Options: {options}")
    df = candles.copy()
    df["atr"] = atr(df, config.ATR_PERIOD)
    func, _ = STRATEGIES[name]
    func(df, config.STRATEGY_SETTINGS[name])
    df["entry_signal"] = df["entry_signal"].fillna(False).astype(bool)
    return df


# ------------------------------------------------- shared loss management

def stop_and_target(entry_price: float, atr_value: float) -> tuple[float, float]:
    """Given an entry, return (stop_loss, take_profit) at 2:1 reward/risk."""
    stop_distance = config.STOP_ATR_MULT * atr_value
    stop_loss = entry_price - stop_distance
    take_profit = entry_price + config.REWARD_RISK * stop_distance
    return stop_loss, take_profit


def position_size(equity: float, entry_price: float, stop_loss: float) -> float:
    """How much BTC to buy so that hitting the stop loses RISK_PER_TRADE
    of the account. Never spends more cash than we have (no leverage)."""
    risk_dollars = equity * config.RISK_PER_TRADE
    per_unit_risk = entry_price - stop_loss
    qty = risk_dollars / per_unit_risk
    # Cap at what we can actually pay for INCLUDING the trading fee,
    # with a hair of headroom so rounding can't push the cost over.
    max_affordable = equity * 0.999 / (entry_price * (1 + config.FEE_RATE))
    return min(qty, max_affordable)
