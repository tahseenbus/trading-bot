# Complete Guide: How to Use the Trading Bot

Everything the bot can do, every command, and the right order to do
things in. For a quick overview see [README.md](README.md).

**The golden rule: this bot only ever touches FAKE money.** It uses free
public price data, needs no account or API keys, and cannot spend a real
cent. It exists so you can learn how algorithmic trading works safely.

---

## 1. One-time setup

You need Python 3.10+ and two libraries:

```
pip install ccxt pandas
```

That's it. No accounts, no API keys, no sign-ups.

---

## 2. The files

| File | What it is |
|---|---|
| `config.py` | **Your control panel.** Every setting lives here — edit and re-run. |
| `strategies.py` | The 12 trading strategies and the shared loss management. |
| `backtest.py` | Tests strategies against real price history. |
| `paper_trade.py` | Trades live prices with fake money. |
| `report.py` | Shows how your paper trading has gone overall. |
| `champion.py` | ALL strategies paper trade in parallel; leaderboard shows who earns. |
| `data.py` | Downloads price data (run directly to test your connection). |
| `trades.csv` | Log of every paper trade (created automatically). |
| `state.json` | The paper trader's memory between restarts (automatic). |
| `portfolios.json` / `champion_trades.csv` | The champion race's memory and trade log. |
| `cache/` | Downloaded price history, so backtests are fast (automatic). |

---

## 3. All commands

### Backtesting (testing on history)

```
python backtest.py
```
Tests the strategy chosen in `config.py` on a RANDOM slice of the last
~2 years. Shows every trade, win rate, profit factor, max drawdown, your
initial investment, and how much you earned or lost. Each run uses a
different random period — that's intentional (see section 5).

```
python backtest.py --list
```
Lists all 12 strategies with one-line descriptions. `*` marks the default.

```
python backtest.py --strategy macd
```
Tests a specific strategy without editing config.py.

```
python backtest.py --seed 42
```
Reproduces a specific run exactly. Every random run prints its seed, so
if you see an interesting result you can study it again.

```
python backtest.py --runs 100
```
**Monte Carlo test**: runs 100 random periods and shows the distribution
— median/best/worst outcome in dollars, % of profitable periods, and how
often it beat simply holding. This is the honest way to judge a strategy;
a single backtest can just be lucky.

```
python backtest.py --compare
```
Races ALL 12 strategies on the same random period. Fun, but one period
proves little — prefer the next command.

```
python backtest.py --compare --runs 50
```
**The most useful command.** Ranks all strategies across 50 random
periods each: median dollars earned, worst case, and how often each was
profitable. Run this before choosing your strategy.

```
python backtest.py --tune
```
Sweeps each setting of your strategy (half to 1.5x its current value)
and reports which values scored best across 30 fixed periods. Treat
results as hints — numbers tuned on the past may not fit the future.

```
python backtest.py --walkforward
```
**The honest tuner.** Tunes settings on one stretch of history, then
measures them on the NEXT stretch the tuner never saw, rolling forward
through all 7 years. If tuned settings can't beat the defaults
out-of-sample, `--tune`'s suggestions are overfitting — the verdict line
tells you which. Run this before adopting anything `--tune` suggests.

```
python backtest.py --symbol ETH/USD
python backtest.py --timeframe 1h
```
Test any Kraken coin (`BTC/USD`, `ETH/USD`, `SOL/USD`, ...) or candle
size (`1m 5m 15m 1h 4h 1d`). Both combine with every mode above, e.g.:
`python backtest.py --compare --runs 50 --symbol ETH/USD`

### Paper trading (live prices, fake money)

```
python paper_trade.py
```
Watches the real market and trades fake money using your config
strategy. Prints a status line every minute: price, portfolio value, and
earned/lost so far. Stop it anytime with Ctrl+C.

```
python paper_trade.py --strategy rsi_reversion --symbol ETH/USD --timeframe 5m
```
Same flags as the backtester. `--iterations 5` runs exactly 5 checks and
exits (handy for a quick look).

The paper trader **remembers everything** in `state.json`: if you stop
it and restart tomorrow, it resumes the same cash, open position, and
initial investment. Delete `state.json` to start over from fresh money.

### Champion / Challenger (all strategies compete live)

```
python champion.py
python champion.py --timeframe 1h --iterations 1
```
Runs ALL 12 strategies as separate $10,000 paper portfolios at the same
time, on live prices, and prints a leaderboard: value, earned/lost,
trades, win rate. After a few weeks, reality — not a backtest — tells
you which strategy actually earns. The GitHub Actions workflow runs this
every hour alongside the main paper trader, so the race collects
evidence 24/7. State lives in `portfolios.json`; delete it to restart
the race.

### Checking results

```
python report.py
```
Your scoreboard: how many trades, current open position with live
unrealized profit/loss, initial investment vs current value, and total
earned or lost. Works while the paper trader runs in another window.

---

## 4. The recommended workflow

1. **Rank the strategies:** `python backtest.py --compare --runs 50`
   (takes a minute — it's simulating 600 backtests). Look at the
   `median $` and `profitable` columns, not just the top line.
2. **Stress-test your pick:** `python backtest.py --runs 100 --strategy <name>`
   — is the median positive? How bad is the worst window? Could you
   stomach that loss?
3. **Optionally tune it:** `python backtest.py --tune --strategy <name>`,
   adopt a suggestion in `config.py` only if it wins by a clear margin.
4. **Set it as default** in `config.py` (`STRATEGY = "<name>"`).
5. **Paper trade it:** `python paper_trade.py`, leave it running, check
   `python report.py` after a few days.
6. **Compare reality to the backtest.** If live results are much worse
   than the Monte Carlo median, the strategy was overfit — go back to 1.

---

## 4b. Running it 24/7 for free on GitHub Actions

The bot can run around the clock on GitHub's servers at no cost — no
computer of your own left on, no credit card, no API keys (it's all fake
money). A scheduled workflow wakes up every hour, does one market check,
and saves the result back to your repo so the next run continues.

**Files that make this work (already in the project):**
- `.github/workflows/trade.yml` — the schedule and steps.
- `requirements.txt` — dependencies GitHub installs.
- `state.json` / `trades.csv` — committed automatically so the bot
  remembers its portfolio between runs.

**One-time setup:**

1. Create a free account at github.com if you don't have one.
2. Create a new **empty** repository (private is fine — hourly runs stay
   well under the free 2,000 minutes/month).
3. In this folder, push the code:
   ```
   git init
   git add -A
   git commit -m "Trading bot"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```
4. On GitHub, open the **Actions** tab and enable workflows if prompted.
5. Click **Paper Trade** → **Run workflow** to start it immediately, or
   just wait for the top of the next hour.

That's it. It now trades every hour forever. To watch it: open the
**Actions** tab to see each run's log, or look at the commit history —
every trade is a commit. Pull the repo and run `python report.py` to see
the scoreboard.

**Good to know:**
- Runs use **hourly candles** (`--timeframe 1h` in the workflow), which
  is the right choice for scheduled hosting — a signal stays valid even
  if GitHub starts the run a few minutes late.
- Change how often it trades by editing the `cron` line in
  `trade.yml` (e.g. `*/15 * * * *` = every 15 min). Faster than hourly
  on a **private** repo can exceed the free minutes — make the repo
  **public** for unlimited minutes (safe here: no secrets in the code).
- GitHub pauses scheduled workflows after 60 days with no repo activity.
  The bot's own commits count as activity, so as long as it trades
  occasionally it stays awake; if it ever pauses, one click re-enables it.
- To stop it: Actions tab → Paper Trade → "..." → Disable workflow.

---

## 5. Understanding the settings (config.py)

### Strategy
- `STRATEGY` — which of the 12 strategies to use by default.
- `STRATEGY_SETTINGS` — each strategy's tuning numbers, with comments
  explaining every one. Units are candles unless noted.

### Loss management (applies to every strategy)
- `STOP_ATR_MULT = 2.0` — stop-loss sits 2 ATRs below entry. ATR is the
  average candle size, so stops widen in wild markets automatically.
  Smaller = tighter stops = more frequent small losses.
- `REWARD_RISK = 2.0` — take-profit at 2x the stop distance: one win
  pays for about two losses.
- `RISK_PER_TRADE = 0.02` — each trade risks 2% of the account. This is
  the setting that keeps a losing streak survivable.
- `TRAILING_STOP` — `True`: no fixed target; the stop follows price up
  and winners run until the trend bends. `False`: classic fixed 2:1.
- `COOLDOWN_CANDLES = 5` — after a losing trade, wait 5 candles before
  buying again (stops revenge-buying into a falling market).
- `MAX_ACCOUNT_LOSS = 0.20` — circuit breaker: down 20% from the initial
  investment, the bot stops opening new trades entirely.

### Money and testing
- `START_CASH = 10_000` — your fake initial investment; all profit/loss
  is measured against it.
- `RANDOM_WINDOW / MIN_WINDOW / MAX_WINDOW` — each backtest picks a
  random 150-550 candle slice. Set `RANDOM_WINDOW = False` to always
  test the full history.
- `DEEP_HISTORY = True` — daily backtests use free Coinbase data from
  2019 onward (7+ years, including full bear markets) instead of
  Kraken's 2-year limit. More conditions tested = less overfitting.
- `USE_MAKER / MAKER_FEE / TAKER_FEE` — with maker mode on, entries and
  take-profits are modeled as resting limit orders (0.16% on Kraken)
  instead of instant market orders (0.26%). Stop-losses always stay
  market orders — they must execute NOW. Cutting fees is one of the few
  near-guaranteed edges in trading. (Not modeled: a resting limit order
  can miss its fill in a fast market.)
- `SLIPPAGE` — market orders fill slightly worse than the printed price.
  Don't set costs to zero; fees are why most strategies lose.
- `TREND_FILTER / TREND_FILTER_SMA` — multi-timeframe confirmation: new
  buys are only allowed while the daily close is above its 50-day
  average. Signals against the daily trend are the classic false-signal
  factory; this refuses them (in backtests AND live).

### Paper trading
- `PAPER_TIMEFRAME = "1m"` — candle size signals form on. 1m is good
  for watching it work; realistic trading uses 1h or 1d.
- `POLL_SECONDS = 60` — how often it checks the market.

---

## 6. Reading the results honestly

- **Win rate is not the goal.** A 35% win rate with 2:1 reward/risk
  makes money; a 60% win rate with tiny wins and huge losses loses it.
  Watch `profit factor` (above 1.0 = profitable) and `expectancy`
  (average dollars per trade).
- **Max drawdown is the pain meter.** A strategy that earns 10% but
  drops 40% along the way is one you'd abandon at the bottom.
- **Compare to buy & hold.** If holding earns more, the strategy isn't
  paying for its complexity. In strong bull markets, holding usually wins
  — what the bot buys you is the capped downside, not extra upside.
- **Different runs give different results on purpose.** Every backtest
  samples a different period. Judge with `--runs`, never one window.

## 7. Troubleshooting

- **"waiting for signal" forever** — normal. Real strategies trade a few
  times per month on daily candles. Use `--timeframe 1m` to see action
  sooner, or `regime_adaptive` which trades more often.
- **Network errors** — the bot prints the error and retries on the next
  poll; it never crashes from a lost connection.
- **Results look too good** — check you didn't set fees/slippage to 0,
  and re-check with `--runs 100`. Suspicion is the correct default.
- **Start over from scratch** — delete `state.json` (fresh money) and
  `trades.csv` (fresh history). Delete `cache/` to force fresh data.
- **Rate limits from Kraken** — rare; the cache keeps requests minimal.
  Wait a minute and retry.

## 8. What this bot deliberately does NOT do

- It never touches real money, exchanges accounts, or API keys.
- It only goes long (buys); it never shorts.
- It trades one coin at a time, one position at a time.
- It is not financial advice, and past results do not predict the future.
  Even the best strategy here can lose for months. That's not a bug in
  the code; that's markets.
