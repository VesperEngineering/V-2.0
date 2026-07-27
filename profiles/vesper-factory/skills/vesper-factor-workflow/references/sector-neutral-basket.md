# Sector-Neutral Basket Generation

## Problem
Global top-4 by combined score can concentrate in one sector. 2026-07-07: MRVL, COHR, MU, LITE — all Semiconductors. Concentrates risk.

## Solution
Pick top-1 ticker from each of the top-4 sectors by highest-scoring ticker.

## Algorithm
```python
by_sector = {}  # {sector: (max_score, ticker)}
for e in scored:
    sec = sectors.get(e["ticker"], "Unknown")
    if sec not in by_sector or e["score"] > by_sector[sec][0]:
        by_sector[sec] = (e["score"], e["ticker"])

ranked = sorted(by_sector.items(), key=lambda x: -x[1][0])[:4]
basket = [(tkr, score, sec) for sec, (score, tkr) in ranked]
```

## Script
`scripts/sector_neutral_basket.py` — loads sector map + factor scores, generates basket MD.
Accepts optional `YYYYMMDD` arg; auto-detects `today - 1` if omitted.
All dates computed as data-date (yesterday's close), same as `run_all_factors.py`.

## Comparison (2026-07-07)
- Global top-4: MRVL, COHR, MU, LITE — 4 in one sector (Semiconductors)
- Sector-neutral: MRVL (IT), FIX (Industrials), BNY (Financials), NCLH (Consumer Discretionary) — 4 distinct sectors

## Cron Wiring (2026-07-08)
The Factor Basket cron wrapper (`~/AppData/Local/hermes/scripts/vesper_factor_basket.py`)
now calls `sector_neutral_basket.py` instead of the old `vesper_factor_basket.py`:

| Before | After |
|---|---|
| `scripts\vesper_factor_basket.py` (NOHR bridge, global top-K) | `scripts\sector_neutral_basket.py` (sector-diverse from factor scores) |

The cron runs at **8:15 AM ET** with the basket retry guard (polls for scores up to 1 hour).
