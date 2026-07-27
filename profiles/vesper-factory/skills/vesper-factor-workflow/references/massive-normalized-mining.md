# Massive Normalized DB — Untapped Column Mining

2026-07-08. Mined all 25 normalized `day_aggs_coverage_expanded_*.sqlite` files (28 total, 25 loaded) against the SP500 OHLCV panel (502 tickers, 5,741 dates, 2003–2026) to discover signals from columns not present in `sp500_ohlcv.sqlite`.

## Untapped Column

| Column | In normalized DB | In SP500 OHLCV panel |
|---|---|---|
| `volume` | ✅ | ✅ |
| `open` / `high` / `low` / `close` | ✅ | ✅ |
| `transactions` (tick count) | ✅ | ❌ **— untapped** |

The `transactions` column is the ONLY column in `day_aggs` not already available in the OHLCV panel. Everything else is redundant.

## Cross-File Join Pattern

The 25 normalized SQLite files each cover the **full date range** (2003→2026) but are **partitioned by ticker cohorts**. Each file adds ~100K more ticker-date matches. Duplicate (ticker, date) keys are overwritten — last file wins. Total matches accumulate to ~29M across all files for 2.48M unique SP500 rows.

```python
for fpath in sorted(norm_files):
    ndb = sqlite3.connect(fpath)
    rows = ndb.execute("""
        SELECT ticker_upper, as_of_date, transactions
        FROM day_aggs
        WHERE ticker_upper IN ('<SP500_TICKERS>')
          AND transactions IS NOT NULL AND transactions > 0
    """).fetchall()
    for ticker, date, trans in rows:
        idx = row_index_lookup[(ticker, date)]
        transactions[idx] = trans  # last write wins
    ndb.close()
```

## Signals Tested (21d horizon, rank IC)

All signals cross-sectionally z-scored per date. Rank IC computed via Spearman against 21d forward returns.

| Signal | IC | IR(m) | t-stat | Source | Unique? |
|---|---|---|---|---|---|
| `transactions_count_cs` | -0.0228 | **-0.7549** | -16.48 | `transactions` | ✅ Novel |
| `avg_trade_size_cs` | -0.0162 | **-0.5008** | -10.93 | `transactions` | ✅ Novel |
| `trans_intensity_cs` | +0.0162 | **+0.5008** | +10.93 | `transactions` | ⚠️ Inverse of avg_trade_size |
| `close_vs_vwap_proxy` | -0.0103 | **-0.2834** | -6.19 | OHLC derived | ✅ |
| `volume_rel_21d` | -0.0029 | -0.1445 | -3.15 | `volume` | — |
| `volume_mom21` | -0.0028 | -0.1369 | -2.98 | `volume` | — |
| `overnight_gap` | -0.0030 | -0.0717 | -1.56 | OHLC derived | — |
| `avg_trade_size_mom21` | -0.0013 | -0.0695 | -1.52 | `transactions` | ✅ |
| `avg_trade_size_z63` | +0.0012 | +0.0594 | +1.29 | `transactions` | ✅ |

## Redundancies

- `avg_trade_size_cs` ≡ `avg_trade_size_raw` ≡ `log_avg_trade_size_cs` — monotonic transforms, identical IC
- `trans_intensity_cs` ≡ `log_trans_per_dollar_cs` — same signal, opposite sign from avg_trade_size
- Only 9 truly unique signals from 12 reported

## Top Discovery: `transactions_count_cs` (IR = -0.75)

Raw tick count. More transactions → lower 21d forward returns. **Strongest signal in the entire mine**, beating all volume-based and OHLC-derived signals. This is a pure liquidity/crowding measure orthogonal to intraday_range and mean_reversion.

Economic interpretation: high-tick-activity stocks are crowded, over-owned, and underperform at medium horizon. Low-tick-activity stocks (quiet, neglected) outperform.

## Second Discovery: `avg_trade_size_cs` (IR = -0.50)

Volume per transaction (average trade size in shares). **Larger trades → lower forward returns.** Institutional/block-trade-dominated stocks underperform retail-favored (small-trade) stocks.

This is the inverse of `trans_intensity_cs` — many small trades per dollar of volume = retail = positive signal.

## Third Discovery: `close_vs_vwap_proxy` (IR = -0.28)

Close deviation from VWAP proxy (H+L+C)/3. **Close below VWAP proxy → mean reversion up.** Classic closing-weakness reversal, distinct from intraday_range.

## Script

`D:/vesper/mine_signals.py` — full mining pipeline: loads SP500 panel, joins 25 normalized DB files, computes 11 signals, runs rank IC at 21d horizon.
