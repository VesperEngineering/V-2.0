# Pipeline Diagnostics — Quick Reference

## The 4-File Cross-Reference

When investigating whether the morning pipeline ran correctly, check these four artifacts:

| # | File | Location | What It Confirms |
|---|---|---|---|
| 1 | `factor_scores_YYYYMMDD.json` | `D:/vesper/data/` | Scores computed? **Check mtime, not filename date.** |
| 2 | `vesper_factor_basket_YYYYMMDD.md` | `D:/vesper/artifacts/evals/` | Basket generated? |
| 3 | `alpaca_receipt_YYYYMMDD.json` | `D:/vesper/artifacts/evals/` | Rebalance fired? 0 orders = stale basket. |
| 4 | `alpaca_portfolio_YYYYMMDD.json` | `D:/vesper/artifacts/evals/` | Actual equity + positions. Ground truth. |

## Date Confusion: Data Date vs Run Date

`run_all_factors.py` writes to `factor_scores_{date.today() - 1 day}.json`. On July 8 morning, it writes to `factor_scores_20260707.json` because the data is July 7's close. **The filename date is always 1 day behind the run date.**

When checking "did scores run today?": look at the file's **modification time**, not its name.

```bash
# Check if scores ran on July 8 morning (expects mtime ~08:30 AM)
ls -la D:/vesper/data/factor_scores_20260707.json
```

## Failure Signatures

| Symptom | Scores File | Basket File | Receipt | Root Cause |
|---|---|---|---|---|
| Basket didn't generate today | ✅ Exists (today's mtime) | ❌ Missing | ⚠️ 0 orders | Basket ran before scores (timing collision) |
| Rebalance did nothing | ✅ Exists | ✅ Exists (stale) | ⚠️ 0 orders | Stale basket, positions matched |
| Pipeline totally missed | ❌ No today's mtime | ❌ Missing | ❌ Missing | Hermes was down, cron didn't fire |
| Portfolio wrong positions | ✅ Exists | ✅ Exists | ✅ Orders placed | Fractional share residuals or execution issue |

## Quick Diagnostic Commands

```bash
# Latest of each artifact
ls -t D:/vesper/data/factor_scores_*.json | head -3
ls -t D:/vesper/artifacts/evals/vesper_factor_basket_*.md | head -3
ls -t D:/vesper/artifacts/evals/alpaca_receipt_*.json | head -3
ls -t D:/vesper/artifacts/evals/alpaca_portfolio_*.json | head -3

# Check today's receipt for orders
python -c "
import json
d = json.load(open('D:/vesper/artifacts/evals/alpaca_receipt_20260708.json'))
print(f'Orders: {len(d.get(\"orders\",[]))}')
print(f'Timestamp: {d.get(\"timestamp\",\"?\")}')
"

# Check portfolio equity + active positions
python -c "
import json
d = json.load(open('D:/vesper/artifacts/evals/alpaca_portfolio_20260708.json'))
print(f'Equity: \${d[\"account\"][\"equity\"]:,.0f}')
active = [p for p in d['positions'] if p['market_value'] > 1]
for p in active:
    print(f'  {p[\"ticker\"]}: \${p[\"market_value\"]:,.0f} (P&L \${p[\"unrealized_pl\"]:,.0f})')
"
```

## Cron Job Quick Check

```bash
# List all cron jobs with last run times
# (via cronjob action='list' in Hermes, or check dashboard Active Jobs panel)

# Key jobs to verify:
# 93d120612d28 — Factor Scores (8:00 AM ET daily)
# ec44f11e95d3 — Factor Basket (8:10 AM ET daily)
# 42fa880a5460 — Alpaca Rebalance (9:35 AM ET Mon-Fri)
# f8fa37b7c1d0 — OHLCV Ingest (7:30 AM Tue-Sat)
```

## Case Study: July 8, 2026 Partial Failure

**Symptoms**: Factor scores for July 7 had mtime of July 8 08:30 (ran today ✓). No `vesper_factor_basket_20260708.md` existed (basket ❌). Rebalance receipt had 0 orders (stale basket ⚠️). Portfolio showed $106,995 (positions matched July 7 basket ✓).

**Root cause**: All three morning jobs slipped to 8:28–8:30 AM. Basket (8:28) ran before scores (8:30), found no fresh scores, produced nothing. Rebalance (9:35) found stale July 7 basket, matched existing positions, placed 0 orders.

**Not a catastrophe**: Scores ran. Portfolio updated (MU +$1,013). Same positions held another day. But on a day when scores would have changed the basket, this would have meant missing a rotation.

**Fix applied**: Basket cron wrapper should check that scores file exists and is fresh before running. See SKILL.md section "Cron Timing Collisions."
