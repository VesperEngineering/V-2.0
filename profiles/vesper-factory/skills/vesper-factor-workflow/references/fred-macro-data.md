# FRED Macro Data — Free Graph CSV Endpoint

The FRED API (`api.stlouisfed.org/fred/...`) requires a registration key
(free to obtain but not zero-effort). The **graph CSV endpoint** works
without any key and returns CSV data.

## URL Pattern

Simpler minimal URL (works for daily/monthly):

```
https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIES_ID}&cosd={START}&coed={END}
```

The full-parameter version found in `app/factors/macro_fred.py` also works.

### Response Format

```
observation_date,{SERIES_ID}
2020-01-01,0.24
2020-02-01,0.17
...
```

**⚠️ Header pitfall**: The column header is `observation_date`, NOT `DATE`.
When parsing, check both:
```python
if len(row) < 2 or row[0] in ("observation_date", "DATE"): continue
```

**Data quirks**:
- Empty values for unreleased dates (e.g., `2026-07-01,`)
- CPIAUCSL has ~1-month reporting lag (May value available in July)
- UNRATE releases ~1st Friday of the month
- Daily series (T10Y2Y) has weekend/holiday gaps — forward-fill

### Series Used

| Series | Frequency | Description |
|---|---|---|
| `T10Y2Y` | Daily | 10-Year Treasury Constant Maturity Minus 2-Year |
| `UNRATE` | Monthly | Unemployment Rate |
| `CPIAUCSL` | Monthly | CPI for All Urban Consumers |

### FM Validation Result (2026-07-08)

Added to `scripts/fama_macbeth.py` with full historical fetch (2004–2026).
Sector-level conditioning via maps in `app/factors/macro_fred.py`.

| Metric | Value |
|---|---|
| FM t-stat | **-1.89** |
| Coefficient | -0.0022 |
| % Positive months | 35% |
| Observations | 169 regressions |
| Significant? | No (misses |t| > 2.0) |

**Verdict**: Borderline. Closest any non-OHLCV factor has come. Stays at weight 0.1.
Not promoted — not killed. Monitor in live IC tracker.
