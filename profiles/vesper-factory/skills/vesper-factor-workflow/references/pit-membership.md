# S&P 500 Point-in-Time Membership

## Source
Wikipedia "List of S&P 500 companies" → "Selected changes" section.
Wikitext API: `https://en.wikipedia.org/w/api.php?action=parse&page=List_of_S%26P_500_companies&prop=wikitext&section=2&format=json`

Covers 402 change events from 1976 to present (additions, removals, ticker changes).

## Algorithm
1. Start with current constituents (`data/sp500_tickers.json`, 502 tickers)
2. Parse changes table (wikitext → structured add/remove events with dates)
3. Iterate changes **backward** (newest → oldest):
   - ADDED ticker → remove from set (wasn't in index before this date)
   - REMOVED ticker → add to set (was in index before)
4. Record membership snapshot at each change date

Result: `vesper_data/sp500_pit_membership.json` — 304 dated snapshots.

## Effective-Date Admission Warning (validated 2026-07-21)

The reverse reconstruction records the **pre-change** membership on the change date, while `get_sp500_members()` uses `bisect_right` and returns that snapshot for the same date and all dates until the next snapshot. This makes the current lookup appear one event late unless the source dates are explicitly defined as post-close announcement dates.

Concrete checks on the generated 2026-07-14 file:
- snapshot `2026-06-22` still had `POOL`/`CPB`, not additions `MRVL`/`FLEX`;
- snapshot `2026-06-24` had the June 22 changes but still had `SATS`, not June 24 addition `ECHO`;
- snapshot `2026-06-30` still included `CAG` despite a June 30 removal row.

Do not use the PIT file for an effective-date backtest until this contract is reconciled against authoritative effective dates and covered by adjacent-date tests. Also verify reproducibility: `scripts/build_sp500_pit_membership.py` was only a wrapper in the audited worktree and its imported `services.sp500_universe_builder` implementation was not present locally.

## Module: `app/services/sp500_pit.py`

```python
from app.services.sp500_pit import get_sp500_members

# Current constituents (502)
curr = get_sp500_members()

# Historical lookup (bisect-right on snapshot dates)
members_2020 = get_sp500_members("2020-01-01")  # 504 tickers
members_2010 = get_sp500_members("2010-03-01")  # 505 tickers

# Dates after last snapshot → current constituents
members_today = get_sp500_members("2026-07-14")  # 502
```

Also exported: `earliest_date()`, `snapshot_count()`, `validate_pit_universe()` (in `position_risk_backtest.py`).

## Data Coverage Limitation

The PIT module identifies **which symbols should be in the index**; it does not establish a tradable permanent security identity or a valid total-return history.

- `sp500_ohlcv.sqlite` is a current-constituent survivor cohort and has poor historical PIT overlap.
- The staged broad Massive day-aggregate database contains many removed/historical ticker strings and materially better overlap, but a join on `ticker_upper` is only an upper bound because raw case collisions, aliases, renames, ticker reuse, and class-share identity remain unresolved.
- The broad staged bars are not by themselves an admitted split/dividend/delisting return panel. Entry and terminal prices, corporate actions, and missing held-security outcomes must fail closed.
- Current `sp500_sectors.json` is not historical sector data.

See `references/pit-five-session-ranking-audit-20260721.md` for measured local coverage and the readiness protocol.

## See also
- `app/services/sp500_pit.py` — PIT membership lookup
- `app/services/position_risk_backtest.py` — `validate_pit_universe()`
- `vesper_data/sp500_pit_membership.json` — 304 dated snapshots
- `vesper_data/sp500_changes_wikitext.txt` — raw Wikipedia wikitext cache