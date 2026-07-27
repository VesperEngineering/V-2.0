# Per-Position Stop-Loss Design

## Status: Complete 3-tier design (2026-07-09, updated with A/B/C comparison)

Full design doc lives at `D:/vesper/docs/STOP_LOSS_DESIGN.md` (404 lines).
This reference is the condensed version for skill-level consultation.

## Design Constraints (from codebase + backtest evidence)

- **No portfolio-level drawdown breakers** — tested in `dd_circuit_breaker.py`, they sell at the bottom and miss recoveries. STATUS.md rule: "Regime filters only." See `references/drawdown-circuit-breaker-pitfall.md`.
- **Factor edge is 10–21 day horizon** — stops must be wide enough to survive noise; tight intraday stops exit before the factor thesis plays out.
- **Equal-weight, ~4 positions, ~25% each** — one position = ~25% of equity. A single blowup is catastrophic. This is WHY per-position stops matter.
- **Paper trading on Alpaca** — can use native Alpaca stop orders.
- **Portfolio snapshot already runs every 5s** during market hours — stop monitor piggybacks on this interval.

## Three-Tier System

### Tier 1: Hard Stop — ATR-Based (set at entry)

- **Stop distance**: 3 × ATR(14) at entry. ATR scales with volatility — MRVL (beta ~1.5) gets more room than BNY (beta ~0.7).
- **Floor**: 12% from entry. **Ceiling**: 20% from entry (25% weight × 20% loss = 5% portfolio hit max).
- **Fallback**: 15% flat if ATR unavailable — never hold without protection due to data issues.
- **Set at**: entry (rebalance day). Does NOT trail. Trailing stops exit too early on factor positions.
- **Order type**: Alpaca `StopOrder` resting on the book (fires automatically, no monitoring loop needed) + local watchdog as secondary defense.
- **If position is increased**: cancel and replace stop with new weighted-average entry. Old stop only covers original qty.
- **Corporate actions**: splits/reverse splits invalidate stop levels — cancel and recreate using current broker state.

```python
atr_14 = average_true_range(ticker, period=14, daily_bars)
stop_pct = clamp(3.0 * atr_14 / entry_price, min=0.12, max=0.20)
stop_price = entry_price * (1.0 - stop_pct)
```

### Tier 2: Time-Based Stop — Factor Decay Monitor

- **Evaluation window**: 15 trading days (~3 weeks). Matches upper end of factor edge horizon.
- **Trigger**: position return ≤ 0% at day 15. If the stock hasn't moved favorably, the signal was likely noise.
- **Action**: Flag for exit at next rebalance (9:35 AM M-F). NOT a panic sell — exclude from `target_tickers` and let rebalance naturally sell.
- **Integration**: `alpaca_rebalance.py` checks `should_time_exit(ticker, entry_date)` before buying.

### Tier 3: Gap/Volatility Circuit Breaker — Per-Position

- **Gap threshold**: -8% gap-down from previous close. Material news usually; factor thesis likely invalidated.
- **Intraday drop threshold**: -10% from previous close during market hours.
- **Check frequency**: every 5-15s (existing portfolio snapshot interval).
- **Action**: Immediate market sell order (not resting stop — gap already happened, resting stop would fill at gap-down price).
- **Cooldown**: Don't re-enter that ticker for 3-5 trading days.
- **Stale data guard**: 60s timeout — don't act on stale prices. Validate symbol and price before firing.

## Partial Fill Handling (Critical — from GPT-5.6 design)

After a stop triggers:
1. Mark position as `STOPPING`
2. Cancel open rebalance orders for the symbol
3. Query actual filled quantity (never trust locally cached position size)
4. Submit sell for remaining quantity only
5. Retry with bounded backoff
6. Mark `STOPPED` only after position confirmed flat

**Never blindly submit repeated full-quantity sell orders** — this can create an unintended short position.

## Rebalance Interaction

Priority at 9:35 AM:
1. Risk controls and stop liquidation
2. Position and order reconciliation
3. Daily factor rebalance
4. New protective-stop placement

Pre-rebalance sequence (9:34:45):
- Pause new order submission
- Reconcile Alpaca positions and open orders
- Evaluate stop state
- Exclude `STOPPING` and `STOPPED` symbols from target basket
- Cancel conflicting orders before placing emergency sells

## Files (design doc at `D:/vesper/docs/STOP_LOSS_DESIGN.md`)

| File | Type | Purpose |
|---|---|---|
| `scripts/stop_registry.py` | New | Stop state management — `data/stop_registry.json` with per-position entry/stop/holding-day/status records |
| `scripts/stop_monitor.py` | New | 5-15s scheduler job — checks Tiers 2 and 3 (Tier 1 is Alpaca resting stop orders) |
| `scripts/alpaca_rebalance.py` | Modified | Adds stop registration at entry, filters time-stopped tickers from targets, cancels old stops for exited positions |
| `scheduler/jobs.json` | Modified | Add "Stop Monitor" job (5-15s, market_hours_only) |

## Key Design Decisions (Why, Not Just What)

- **"Disaster stop, not trading signal"** — this stop should NOT exit every losing position. It exists for single-name blowups, overnight gaps, bad data/model/order state, and abnormal moves that invalidate the position-sizing assumption.
- **ATR-scaled, not fixed %**: Fixed 10% stop on MRVL gets hit on a normal down day; on BNY it rarely fires. ATR normalizes to each stock's own volatility.
- **12% floor**: Below 12% converts normal volatility in names like SMCI, VRT, HOOD into repeated forced exits. The portfolio's actual stocks need wide stops.
- **No trailing stops**: Factor thesis needs 10–21 days. Trailing stops exit on normal volatility before the signal plays out.
- **Time stops exit at next rebalance, not mid-day**: Preserves orderly execution. A flat position after 3 weeks = signal-invalidity exit, not a panic sell.
- **Gap breaker uses immediate market order**: A gap has already happened — a resting stop would trigger at a bad price. Exit at first available price.
- **Broker-native + local watchdog dual layer**: If Python dies, Alpaca's server-side stop still fires. If Alpaca rejects/cancels the stop, local watchdog catches it.
- **Floor 12% / ceiling 20%**: Caps worst case at 5% portfolio hit per position (25% weight × 20% loss). Portfolio impact: $3,240-$5,400 per stop, 2.9-4.8% of equity.

## Parameter Summary

| Parameter | Value | Tier | Tunable? |
|---|---|---|---|
| ATR multiplier | 3.0× | 1 | Yes — test 2.5–4.0 in backtest |
| Min stop distance | 12% | 1 | Don't go below 8% for factor positions |
| Max stop distance | 20% | 1 | Hard ceiling |
| Fallback stop distance | 15% | 1 | Used when ATR unavailable |
| Time stop window | 15 trading days | 2 | Test 10–21d |
| Time stop return threshold | 0% | 2 | Could raise to +2% |
| Gap-down threshold | -8% | 3 | Test 6–10% |
| Intraday drop threshold | -10% | 3 | Test 8–12% |
| Gap cooldown | 3-5 trading days | 3 | Prevents whipsaw re-entry |
| Stale data timeout | 60s | 3 | Don't act on stale prices |
| Monitor interval | 5-15s | 3 | Faster only if API supports it |

## Backtest Validation (before deploying live)

Validate each tier against the Massive OHLCV history (2005–2026) via `scripts/backtest_stops.py`:
- **Tier 1**: simulate daily-low touches stop → exit at stop price. Compare Sharpe/max DD with vs without stops.
- **Tier 2**: for positions held 15+ days with return ≤ 0%, measure what return would have been if held to 21d rebalance.
- **Tier 3**: find all -8%+ gap / -10%+ intraday drop instances, measure 5-day recovery rate vs continued decline.

Expected: slightly lower returns (stops cost money normally), but significantly reduced max drawdown (currently -59% without stops).

## Model Comparison (2026-07-09)

Eight blind designs were produced comparing GLM-5.2, DeepSeek, and 6 GPT-5.6 variants. Full 8-model results in `references/model-comparison-2026-07-09.md`.

### Original 3-model summary (GLM-5.2 vs DeepSeek vs GPT-5.6 luna-pro)

| Aspect | GLM-5.2 | DeepSeek | GPT-5.6 (winner) |
|---|---|---|---|
| ATR multiplier | 2.5× | 2.0× | 3.0× |
| Floor / ceiling | none | 8% / 20% | 12% / 20% |
| Action | Trim 50% | Full exit | Full exit |
| Time stop | ❌ | ✅ (15d) | ❌ |
| Partial fills | ❌ | ❌ | ✅ (6-step) |
| Broker outage | ❌ | ❌ | ✅ (dual layer) |
| Stop qty staleness | ❌ | ❌ | ✅ |
| Corporate actions | ❌ | ❌ | ✅ |
| Multi-stop pause | ✅ | ❌ | ❌ |
| Day-1 exemption | ✅ | ❌ | ❌ |
| Portfolio impact math | ❌ | ❌ | ✅ ($3,240-$5,400) |

**Key lesson**: The winning design wasn't smarter math — it was deeper operational awareness. Production risk management fails on edge cases (partial fills, stale stops, broker outage), not on trigger formulas. When designing risk systems, spend 80% of effort on failure modes, not on parameters.

The 3-tier design above incorporates the best of all three: GPT-5.6's operational rigor + DeepSeek's time stop + the 12-20% clamp range (consensus across all three: floor 8-12%, ceiling 20%).

### How to run the comparison yourself

```python
import requests
# Get OpenRouter key from ~/.hermes/.env (OPENROUTER_API_KEY)
# Query OpenRouter directly for the model
resp = requests.post(
    'https://openrouter.ai/api/v1/chat/completions',
    headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
    json={
        'model': 'openai/gpt-5.6-luna-pro',  # $1/M in, $6/M out
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 4000,
    },
    timeout=180,
)
```

Model variants on OpenRouter (as of 2026-07-09):
- `gpt-5.6-luna` / `gpt-5.6-luna-pro`: $1/$6 per M tokens (cheapest)
- `gpt-5.6-terra` / `gpt-5.6-terra-pro`: $2.50/$15 per M tokens
- `gpt-5.6-sol` / `gpt-5.6-sol-pro`: $5/$30 per M tokens

A single design prompt costs ~$0.09 on luna-pro.
