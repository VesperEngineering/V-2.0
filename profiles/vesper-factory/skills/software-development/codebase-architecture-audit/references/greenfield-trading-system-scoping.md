# Greenfield Trading System Scoping — Data, IC, Universe

Session-specific guidance for early-stage quant trading system decisions, drawn from the v20 Vesper skeleton review (2026-07-21).

## 1. Data Source Decision: Free vs. Paid

**Rule: Don't buy premium data until the system runs and the strategy validates on free data.**

### Free Tier Stack (Sufficient for 0 → 1)

| Source | Use Case | Limitations |
|--------|----------|-------------|
| **yfinance** | Backtesting, daily bars, universe screening | Delayed, rate limits, occasional gaps |
| **Alpaca Data API** | Paper trading, real-time-ish quotes (15min delay on free) | Requires Alpaca account, limited history |
| **Polygon.io** | WebSocket real-time (later) | Free tier: 5 calls/min |
| **Tiingo** | EOD + intraday | 500 req/day free |
| **Finnhub** | Real-time quotes | 60 calls/min free, limited history |

**When to upgrade to Massive/Polygon paid:**
- After 2+ weeks of live paper trading with IC ≈ backtest IC (±0.01)
- When slippage/execution costs exceed data subscription cost
- When you need WebSocket real-time (not REST polling)
- When universe expands beyond 200 stocks and rate limits bind

**Cost-benefit:** $200/month = $2,400/year. A $50k account needs ~5% annual return just to cover data. Prove the edge first.

## 2. IC (Information Coefficient) Targets

IC = Spearman rank correlation between predicted and actual forward returns.

| IC Range | Interpretation | Action |
|----------|----------------|--------|
| 0.02–0.05 | Weak but tradeable | ✅ Realistic target for daily rebalancing |
| 0.05–0.10 | Good alpha | ✅ Achievable with proper features |
| 0.10–0.15 | Very good | ⚠️ Hard to sustain, check for bias |
| > 0.15 | Suspicious | 🚩 Almost certainly overfitting or look-ahead |

**Realistic target: IC = 0.03–0.06** for daily cross-sectional ranking on liquid US equities.

**What matters more than raw IC:**
- **IC decay** — how fast does the signal lose power? (rank IC by horizon)
- **Turnover cost** — IC 0.05 with 100% daily turnover loses to 10bps round-trip costs
- **Capacity** — can you execute at your capital size?

**Rule of thumb:** With IC = 0.05, daily rebalancing, $50k capital, you need **< 20% annual turnover** to overcome costs.

## 3. Universe Size: Breadth vs. Depth

The Fundamental Law of Active Management:
```
IR ≈ IC × √Breadth × Transfer Coefficient
```

| Universe | Independent Bets/Year | IC for IR=1.0 | Pros | Cons |
|----------|----------------------|---------------|------|------|
| 20 | 5,040 | 0.014 | Deep research possible | Concentrated, regime-sensitive, one earnings miss kills you |
| 100 | 25,200 | 0.006 | Good balance | Sector-concentrated |
| 200 | 50,400 | 0.004 | Diversified, robust | Manageable data |
| 500 | 126,000 | 0.003 | High breadth | Data/compute heavy |
| 1000 | 252,000 | 0.002 | Maximum breadth | Diluted alpha, expensive, slippage |

**Recommendation: 100–200 stocks**

Why:
- **20 stocks** is too concentrated for cross-sectional momentum/ML ranking — you need spread to rank meaningfully
- **1000 stocks** is overkill for $50k — API rate limits, data costs, and slippage eat the marginal breadth gain
- **100–200** gives ~20–30 names per sector, enough for ranking, manageable for a retail account

**Practical setup:**
```yaml
universe: 150 stocks  # S&P 500 top 150 by market cap
top_n: 10             # hold 10 positions
rebalance: daily      # or 30min during market hours
```

## 4. Common Greenfield Skeleton Pitfalls (from v20 review)

These are the exact failure modes found in a fresh trading system skeleton:

| Pitfall | Severity | Fix |
|---------|----------|-----|
| `.env.example` contains real API keys | 🔴 CRITICAL | Rotate immediately, use placeholders |
| `strategy.name: ml_model` but engine only supports `momentum` | 🔴 CRITICAL | Wire ML strategy or change config |
| `dashboard/app.py` is 0 bytes | 🔴 CRITICAL | Implement or stub before paper trading |
| `data.provider: Massive` but feed only supports `yfinance`/`custom` | 🔴 CRITICAL | Fix provider string or implement feed |
| Missing `train_model.py` + `models/` dir | 🟡 HIGH | Create before ML strategy can run |
| `IGNORE RUN.txt` is accidental config paste | 🟡 MEDIUM | Delete, merge into README |
| Position sizing uses `signal.strength` which is ~0.9+ for all signals | 🟡 MEDIUM | Rethink strength → sizing mapping |
| No rate limiting on data feed | 🟡 MEDIUM | Add caching/throttling before live |
| `datetime.utcnow()` deprecated | 🟢 LOW | Replace with `datetime.now(timezone.utc)` |
| Universe builder has duplicate symbols | 🟢 LOW | Deduplicate candidate list |

## 5. Validation Sequence (Before Spending Money)

```
Phase 1: Fix skeleton     → system starts without crash
Phase 2: Backtest         → IC > 0.03, Sharpe > 0.8 after costs
Phase 3: Paper trade 2wk  → live IC ≈ backtest IC (±0.01)
Phase 4: Go live small    → $5k, measure slippage vs. backtest
Phase 5: Scale            → then consider premium data, larger universe
```

**Never skip Phase 3.** The gap between backtest and live paper is where most retail strategies die.

## 6. Key Insight: The Bottleneck Is Not Data

The user's instinct was to spend $200 on data. The real bottleneck was:
1. Empty dashboard file (system won't start)
2. ML strategy not wired (config says one thing, code does another)
3. No training script (model doesn't exist)
4. Invalid provider string (feed crashes on startup)

**Fix the skeleton. Prove the edge. Then buy better data.**
