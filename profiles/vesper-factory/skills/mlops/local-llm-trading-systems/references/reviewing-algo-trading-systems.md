# Reviewing Non-LLM Algo Trading Systems

Class-level guidance for when the user shares a **standalone algorithmic trading codebase** (not LLM-augmented, not Vesper Quant / Vesper Swing) and asks for architecture review, strategy design advice, or phased build plans. The user's own systems (e.g. a `v20` folder with engine/data/strategy/risk/execution/dashboard) follow a recognizable pattern and the same questions recur.

## When to use

- User drops a folder path containing a trading engine and asks "what do you think"
- User asks about universe size, IC targets, data-source selection, or risk-limit defaults for a NEW system
- User is deciding whether to pay for a data feed vs. stick with free sources
- The system is traditional signal-engine → risk → broker, no LLM in the loop (if LLM is involved, also load `local-llm-trading-systems`)

## High-Signal Architecture Review Checklist

Walk these in order — they catch the most bugs per minute:

1. **Credentials** — `.env.example`, `config/*.yaml`, any hardcoded key string. Real-looking keys in a repo template are an immediate rotation trigger. Flag them loudly.
2. **Config ↔ code contract** — every string the code `config.get(...)`s must match the YAML schema. Common breaks:
   - `strategy.name: ml_model` in YAML but engine only implements `momentum` → startup crash
   - `data.provider: Massive` but feed factory only knows `yfinance | custom` → startup crash
3. **Empty / stub files imported by entry points** — `dashboard/app.py` of 0 bytes imported by `run_paper.py` is a startup crash.
4. **Referenced-but-missing scripts** — search for `scripts/*.py` references in error messages and docstrings (`train_model.py`, `build_universe.py`) and confirm they exist.
5. **Universe vs. strategy mismatch** — 21 symbols for a cross-sectional momentum/rank strategy is too narrow; the algorithm's edge requires breadth. See "Universe sizing" below.
6. **Data-fetch frequency vs. rate limits** — tick loop at N-second intervals calling `feed.get_bars()` for the whole universe will hit yfinance rate limits. Strategy-level `rebalance_interval` gates signals but NOT data fetches.
7. **Position sizing sanity** — `signal.strength` often collapses to `~0.9+` for top-ranked names, making `pv * pct * strength` nearly constant. Sizing barely differentiates signals; flag the formula.
8. **`datetime.utcnow()` usage** — deprecated in 3.12+, recommend `datetime.now(timezone.utc)`.
9. **Audit/logger file handles** — text-mode opens without `encoding="utf-8"` on Windows default to cp1252 and can crash on unicode.
10. **Mutable-state reconciliation** — `StateManager.reconcile` writing to `_private` fields of risk/circuit-breaker objects instead of going through a setter / restore API.

## Data Source Decision Tree

The user often asks "should I pay for data?" The answer is **almost always no until the system runs end-to-end and the strategy validates**.

| Tier | Source | Cost | When to use |
|---|---|---|---|
| Free | **yfinance** | $0 | Backtesting, initial paper trading. Already wired into most systems. Rate-limited, delayed, occasionally gappy. |
| Free w/ account | **Alpaca Data API** | $0 | Live paper trading against the same broker you'll trade real money with. 15-min delay on free tier. Natural fit if broker is already Alpaca. |
| $29/mo | Massive Starter | cheap | 15-min delayed. Skip — same as Alpaca free. |
| $79/mo | Massive Developer | mid | Still 15-min delayed. Skip. |
| **$199/mo** | Massive Advanced | expensive | **Real-time WebSockets.** Only tier worth paying for. Only when (a) system runs end-to-end, (b) backtest + paper show edge, (c) intraday strategy needs real-time. |
| Free tier | Polygon.io | $0 | 5 calls/min — too slow for live. OK for ad-hoc historical pulls. |
| Free tier | Finnhub | $0 | 60 calls/min, real-time quotes, limited history. Useful as a secondary quote validator. |

**Rule of thumb:** if the dashboard file is empty, the ML strategy isn't wired in, and the config has a stray API key in it — the user should not be paying for data yet. Fix the plumbing on yfinance free first.

## IC (Information Coefficient) Targets

IC = Spearman rank correlation between predictions and realized forward returns. Realistic targets for daily-rebalanced US equity strategies:

| IC | Interpretation | Action |
|---|---|---|
| 0.02–0.05 | Weak but tradeable with good risk management | ✅ Target for a first working strategy |
| 0.05–0.10 | Solid alpha | ✅ Achievable with proper feature engineering |
| 0.10–0.15 | Institutional quality | ⚠️ Hard to sustain, monitor for regime decay |
| > 0.15 | Suspicious | 🚩 Almost always look-ahead bias or overfitting — audit features |

**What matters more than raw IC:**
- **IC decay** — how fast does the signal lose predictive power over holding period?
- **Turnover cost** — IC 0.05 with 100% daily turnover loses money to commissions/slippage. With ~10bps round-trip cost, need turnover < ~20%/year at $50k to break even.
- **Capacity** — can you actually execute the strategy at the intended AUM?

## Universe Sizing (Fundamental Law of Active Management)

```
IR ≈ IC × √Breadth × Transfer Coefficient
```

Breadth = number of independent bets per year. For daily rebalancing on `N` stocks: `breadth = N × 252`.

| Universe | Bets/year | IC needed for IR=1.0 | Verdict |
|---|---|---|---|
| 20 | 5,040 | 0.014 | Too concentrated. One earnings miss kills the book. Not enough spread for cross-sectional ranking. |
| **100–200** | 25,200–50,400 | 0.003–0.006 | **Recommended.** ~20–30 names/sector, meaningful ranking, manageable data, ~10 positions held out of 100+ candidates. |
| 500 | 126,000 | 0.003 | Fine but diminishing returns. Data/compute heavy. |
| 1000 | 252,000 | 0.002 | Overkill for small accounts. Dilutes alpha, high turnover, high data cost. |

**Practical recommendation:** S&P 500 top 150 by market cap, hold top 10 by signal, daily rebalance. Enough breadth for the LLN to work without drowning in data costs.

## Phased Build Plan (canonical)

When the user asks "what next?" the answer follows this shape:

1. **Fix the system** — credentials, config/code contract, empty files, missing scripts. Goal: starts without crashing.
2. **Validate strategy** — write `train_model.py` if ML, backtest on yfinance over 2 years, measure IC + turnover + Sharpe + max DD. Gate: IC > 0.03 AND Sharpe > 0.8 after costs.
3. **Paper trade** — live paper against Alpaca data feed. Track slippage vs. backtest. Gate: live IC ≈ backtest IC (±0.01).
4. **Go live small** — only after paper validates. $3–5K, fractional shares, tight risk.
5. **Scale** — only after live P&L is positive for a meaningful window. NOW consider paid data, larger universe, more capital.

**Anti-pattern to call out:** paying for data / scaling universe / raising capital before phase 2 gates pass.

## Red Flags to Always Surface

- Real-looking API keys in `.env.example` or anywhere committed
- `IGNORE RUN.txt`-style files that are clearly stray pastes of config content
- Backtest scripts that hardcode a different strategy than the config specifies
- Universe builder scripts with duplicate tickers in candidate lists (e.g. RBLX, AIG, JPM appearing twice in the same list)
- Strategy code with strength formulas that saturate near 1.0 for all top-ranked names (defeats position sizing)
- Tick loops that fetch full-universe bars every few seconds — rate-limit death
- Circuit breakers / risk monitors that get their state restored via `_private` attribute pokes from a state manager

## Tone for the Review Report

User prefers: brutally honest severity grading (🔴 critical / 🟡 design / 🟢 good), numbered findings, a quick-fix priority table, and a clear bottom-line assessment. Don't soft-pedal — if three separate issues prevent the system from starting, say so.
