# All the bot's settings in one place. Edit anything here, then re-run.

# Market to trade. Kraken's public data API is free, needs no account,
# and works from the US.
EXCHANGE = "kraken"
SYMBOL = "BTC/USD"

# ------------------------------------------------------------ strategy
# Which strategy the bot uses. Run  python backtest.py --list  to see all,
# or override one run with  python backtest.py --strategy macd
#
# Options: breakout, sma_cross, ema_cross, macd, rsi_reversion,
#          bollinger_reversion, bollinger_breakout, momentum,
#          volume_breakout, stochastic, macd_rsi, regime_adaptive
STRATEGY = "rsi_reversion"

# Tuning numbers for every strategy. Units are candles unless noted.
STRATEGY_SETTINGS = {
    # Buy a close above the last `lookback` candles' high, but only while
    # price is above the `trend_sma` average (uptrend filter).
    "breakout": {"lookback": 20, "trend_sma": 100},

    # Buy when the fast moving average crosses above the slow one.
    "sma_cross": {"fast": 10, "slow": 30},
    "ema_cross": {"fast": 12, "slow": 26},

    # Buy when the MACD line crosses above its signal line.
    "macd": {"fast": 12, "slow": 26, "signal": 9},

    # Buy when RSI drops below `oversold` while still in an uptrend.
    "rsi_reversion": {"period": 14, "oversold": 45, "trend_sma": 50},

    # Bollinger bands: average +/- `num_std` standard deviations.
    # reversion buys below the lower band; breakout buys above the upper.
    "bollinger_reversion": {"period": 20, "num_std": 2.0},
    "bollinger_breakout": {"period": 20, "num_std": 2.0},

    # Buy when price gained more than `min_change` (5% = 0.05) over
    # the last `lookback` candles.
    "momentum": {"lookback": 10, "min_change": 0.05},

    # Breakout that also needs volume `volume_mult` times above average.
    "volume_breakout": {"lookback": 20, "volume_mult": 2.0},

    # Buy when stochastic %K crosses above %D while below `oversold`.
    "stochastic": {"k_period": 14, "d_period": 3, "oversold": 25},

    # Combo: MACD cross, but only when RSI is below `rsi_max` so we
    # don't buy moves that are already overextended.
    "macd_rsi": {"fast": 12, "slow": 26, "signal": 9,
                 "rsi_period": 14, "rsi_max": 60},

    # Meta-strategy: ADX above `adx_threshold` = trending market -> trade
    # breakouts; below = ranging market -> buy oversold dips.
    "regime_adaptive": {"adx_period": 17, "adx_threshold": 25,
                        "lookback": 20, "rsi_period": 14, "oversold": 37},
}

# ------------------------------------- loss management (all strategies)
# Stop-loss sits STOP_ATR_MULT ATRs below entry (ATR = average true range,
# a measure of recent volatility). Take-profit sits REWARD_RISK times the
# stop distance above entry, so one win recovers about two losses.
ATR_PERIOD = 14
STOP_ATR_MULT = 2.0
REWARD_RISK = 2.0

# Each trade risks only this fraction of the portfolio. If the stop is hit
# you lose ~2% of the account; if the target is hit you gain ~4%.
RISK_PER_TRADE = 0.02

# Trailing stop: instead of a fixed take-profit, the stop-loss follows the
# price up (always STOP_ATR_MULT ATRs below the latest close, never moving
# down). Winners run until the trend bends; there is no fixed target.
# False = classic fixed 2:1 stop/target (the default).
TRAILING_STOP = True

# After a LOSING trade, wait this many candles before buying again.
# Stops the bot from instantly re-buying into the same falling market
# that just stopped it out. 0 = no cooldown.
COOLDOWN_CANDLES = 5

# Circuit breaker: if the portfolio has lost this fraction of the initial
# investment, the bot stops opening NEW positions (existing stops still
# run). A hard cap on how wrong things can go. 0.20 = stop at -20%.
MAX_ACCOUNT_LOSS = 0.20

# ------------------------------------------------------------ backtest
BACKTEST_TIMEFRAME = "1d"   # daily candles (~2 years of free history)
FEE_RATE = 0.0026           # 0.26% per trade (Kraken's standard taker fee)
SLIPPAGE = 0.0005           # 0.05%: real fills are slightly worse than the
                            # printed price. Buys cost a touch more, sells
                            # get a touch less. Keeps backtests honest.

# Random-window backtesting: each run tests the strategy on a different
# randomly chosen slice of the available history, so you can see how it
# behaves across many different market periods instead of always the same
# one. Set RANDOM_WINDOW = False to always use the full history.
RANDOM_WINDOW = True
MIN_WINDOW = 150            # shortest slice (in candles) a run may pick
MAX_WINDOW = 550            # longest slice a run may pick

# ---------------------------------------------------------- your money
# Initial investment (fake USD). Both the backtest and the paper trader
# start with this and report profit/loss against it.
START_CASH = 10_000

# ------------------------------------------------------- paper trading
PAPER_TIMEFRAME = "1m"      # 1-minute candles so you see activity quickly
POLL_SECONDS = 60           # how often to check the market
