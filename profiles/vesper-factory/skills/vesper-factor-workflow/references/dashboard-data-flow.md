# Dashboard Data Flow & Schema Mapping

## The chain

```
factor_scores_YYYYMMDD.json  (2 scoring systems, different detail keys)
         │
         ▼
    aggregator.py            (reads latest scores, maps to dashboard columns)
         │
         ▼
  dashboard_data.json        (served to browser)
         │
         ▼
   data-binder.js            (renders into HTML table)
         │
         ▼
    index.html               (column headers + tbody target)
```

## Two factor scoring systems — different detail keys

### System A: Registry-based (`run_all_factors.py` via cron, ~29 tickers, old)
```json
{"details": {"technical": 2.32, "sentiment": 0.98, "insider": 0, "massive": 0.37}}
```

### System B: IC-weighted pipeline (`run_all_factors.py` with IC weights, ~512 tickers, production)
```json
{"details": {"sp500_technical": 3.0, "finviz_sentiment": 1.11, "wiki_attention": 0.43, "sec_fundamentals": 0, "insider": 0, "massive": 0}}
```

The aggregator picks the LATEST scores file (by mtime). System B (512 tickers) almost always wins.

## Aggregator key mapping (MUST match data-binder.js)

The aggregator emits these keys. data-binder.js renders them. They MUST match:

| aggregator key | Source in details dict | JS column | Current HTML header |
|---|---|---|---|
| `entropy` | `sp500_technical` → `entropy` → `technical` (fallback chain) | Trend + Entropy | ENTROPY |
| `hurst` | `sec_fundamentals` | Hurst | HURST |
| `vol` | `wiki_attention` | Vol | VOL |
| `sent` | `finviz_sentiment` → `sentiment` | Sent | SENT |
| `insider` | `insider` | Insider | INSIDER |
| `massive` | `massive` | Massive (dot) | MASSIVE |
| `top_factor` | Computed: max(abs()) of all factors | Top | TOP |

## Common trap: aggregator/data-binder key mismatch

If aggregator outputs `tech/fund/wiki` but JS expects `entropy/hurst/vol`, ALL columns show 0.000 or "—".

**Debug**: check `dashboard_data.json` with:
```python
d = json.load(open('dashboard_data.json'))
print(list(d['factor_leaders']['leaders'][0].keys()))
```

Expected: `['rank','ticker','score','entropy','hurst','vol','sent','insider','massive','top_factor']`

If you see `['rank','ticker','score','tech','fund','wiki','sent','insider','massive']` — keys don't match. Fix the aggregator.

## Top Factor column

Aggregator computes `top_factor` by finding the factor with the largest absolute detail value:
```python
cols = {'Tech': details.get('sp500_technical') or ...,
        'Fund': details.get('sec_fundamentals', 0),
        'Wiki': details.get('wiki_attention', 0),
        'Sent': details.get('finviz_sentiment') or ...,
        'Insdr': details.get('insider', 0),
        'Mass': details.get('massive', 0)}
best = max(cols, key=lambda k: abs(cols[k]))
leader['top_factor'] = best if abs(cols[best]) > 0 else '—'
```

JS renders: `r.top_factor || "—"` — if missing, shows "—".

## Data coverage (System B, 512 tickers, Jul 2026)

| Factor | Coverage | Ticker count |
|---|---|---|
| `sp500_technical` | 500 | entropy column |
| `finviz_sentiment` | 502 | sent column |
| `wiki_attention` | 501 | vol column |
| `massive` | 498 | massive column |
| `sec_fundamentals` | 394 | hurst column |
| `insider` | 90 | insider column |

Columns showing 0.000 for a ticker usually means that factor doesn't cover that ticker — not a bug.