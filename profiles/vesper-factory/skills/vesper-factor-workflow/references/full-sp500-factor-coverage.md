# Full S&P 500 Factor Coverage (v1.2, 2026-07-07)

How single-factor dominance (430/474 tickers with only `sp500_technical`) was fixed →
499/512 tickers with 3+ independent factors. Recipes + pitfalls for each expansion.

## 1. Wikipedia article map — `scripts/build_wiki_article_map.py`

One API call fetches the wikitext of "List of S&P 500 companies"; each constituent
row links the company article (exact titles, no guessing):

```
https://en.wikipedia.org/w/api.php?action=parse&page=List_of_S%26P_500_companies&prop=wikitext&format=json&formatversion=2
```

Parsing pitfalls (all hit in practice):
- Rows use `{{NyseSymbol|MMM}}` / `{{NasdaqSymbol|ADBE}}` templates → regex
  `\{\{[A-Za-z]*[Ss]ymbol\|([A-Z]{1,5}(?:\.[A-Z])?)\}\}`. A NYSE/Nasdaq-prefix-only
  regex catches barely a third of rows.
- The page has a SECOND table ("Selected changes") full of delisted tickers.
  Filter rows on the 10-digit CIK (`\b\d{10}\b`) — only constituent rows have one.
- Keep DOT ticker form (`BRK.B`), matching the Massive OHLCV DB. Do NOT normalize
  to `BRK-B` — that orphans the ticker from every price-based factor.

Output: `data/wiki_article_map.json` `{"count": N, "map": {ticker: Article_Title}}`,
~502 entries (dual share classes like GOOG/GOOGL map to the same article).

`data/sp500_tickers.json` is regenerated from the map keys — the two files must
stay in sync. The old hand-maintained list had drifted badly (missing HD/DIS/WBD/XOM,
containing garbage like "APARTMENT" and 65 delisted names).

## 2. wiki_attention factor 30 → 501 tickers (`app/factors/wiki.py`)

- Loads the article map (falls back to a 30-ticker hardcoded dict if missing/<100).
- Parallel fetch: `ThreadPoolExecutor(max_workers=8)`. 16 workers triggered
  Wikimedia 429s; 8 workers + retry is the sweet spot (~23s for 500 tickers).
- **Percent-encode article titles**: `quote(article, safe='')`. Titles with `&`,
  commas, dots (`Johnson_&_Johnson`, `Tesla,_Inc.`) fail as raw URL segments —
  this alone cost ~200 tickers.
- **429 retry**: up to 4 attempts, backoff `1.5 * (attempt+1)` seconds. Despite
  "no rate limit" folklore, Wikimedia does 429 under parallel load.
- Raise the factor's pipeline timeout: `wiki_attention: 90` in FACTOR_TIMEOUTS
  (was 30 — the expanded factor takes ~23s + subprocess overhead).

## 3. sec_fundamentals factor — NEW, 394 tickers, 4s, zero network

`app/factors/sec_fundamentals.py`. Reads `artifacts/db/sqlite-analyst.db :: sec_facts`
(4.2M rows, SEC bulk companyfacts). Free data that was sitting unused.

- Revenue tag is split across TWO us-gaap tags — query both:
  `Revenues` OR `RevenueFromContractWithCustomerExcludingAssessedTax`.
- Annual series query: `fiscal_period='FY' AND fiscal_year>=2023`, `MAX(value)`
  grouped by (ticker, fiscal_year) — sec_facts has duplicate rows per period
  from restatements/multiple filings.
- Four sub-signals, each z-scored cross-sectionally then averaged:
  revenue growth (latest FY vs prior FY), net margin (NI/Rev), ROE (NI/Equity),
  asset turnover (Rev/Assets).
- Sanity-bound raw ratios before z-scoring (growth ∈ (-0.9, 3.0), margin ∈ (-2, 1),
  ROE ∈ (-3, 3)) and clip z at ±3 — SEC data has wild outliers.
- Registered in `app/factors/registry.py`; FACTOR_TIMEOUTS `sec_fundamentals: 60`.

## 4. massive factor 29 → 499 tickers (`app/factors/massive.py` v2)

Old version read the 33-ticker reference DB. v2 reads
`vesper_data/massive/sp500/sp500_ohlcv.sqlite` (full SP500):
- 20-day momentum: close vs series[20] (rows fetched `ORDER BY ticker, date DESC`,
  grouped in Python — one query, 0.5s total).
- Volume surge: `log(mean(vol[:5]) / mean(vol[:60]))`.
- Log market cap from the reference DB where available (partial coverage is fine —
  each sub-signal is z-scored independently, then per-ticker average over
  available signals only).
- Skip tickers with <25 rows of history.

## 5. Score combination fix (`scripts/run_all_factors.py`)

Old: `r.scores.get(ticker, 0.0)` — every factor voted 0 on tickers it didn't
cover, dragging well-covered tickers toward zero while 1-factor tickers kept
their raw z-score and dominated extreme ranks.
New: only include factors where `ticker in r.scores`; average over that subset.
Missing coverage = no opinion, not a zero vote.

## 6. OHLCV DB reconciliation (no re-download needed)

The raw Massive daily CSVs are cached at `vesper_data/massive/sp500/2026*.csv.gz`
(each file = ALL US tickers). After a universe change, re-ingest locally:
filter each CSV against the new ticker set, `INSERT OR REPLACE` into
`sp500_ohlcv`, then `DELETE` tickers no longer in the universe + `VACUUM`.
125 cached files re-ingested in ~1 min → 502/502 constituents covered.
(Deeper history back to 2003 exists at `vesper_data/massive/raw/us_stocks_sip/day_aggs_v1/` —
5,730 files — check there before downloading for backtests.)

## Verification one-liner

```python
import json
from collections import Counter
d = json.load(open('data/factor_scores_YYYYMMDD.json'))
c = Counter(len(e['details']) for e in d['scored'])
print(dict(sorted(c.items())))  # want mass at 3+; a spike at 1 means coverage regressed
```
