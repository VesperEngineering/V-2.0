# Six-Factor Registry (Vesper v1.0 — 2026-07-06)

## Registered Factors

Default registry in `app/factors/registry.py`:

```python
_default.register_all(
    TechnicalFactor(),
    SentimentFactor(),
    InsiderFactor(),
    GoogleTrendsFactor(),   # ⏸️ rate-limited (429), kept as fallback
    WhaleFactor(),           # 🔲 SEC EDGAR browse needs cooldown
    WikiFactor(),            # ✅ Wikipedia pageviews (replaces Google Trends)
)
```

| # | Name | Source | Free? | Tickers | Status |
|---|------|--------|-------|---------|--------|
| 1 | `technical` | OHLCV entropy, hurst, realized_vol | ✅ | 14 | ✅ Active |
| 2 | `sentiment` | WebZ + FinViz news | ✅ | 30 | ✅ Active |
| 3 | `insider` | SEC Form 4 EDGAR daily index | ✅ | 4 | ✅ Active |
| 4 | `wiki_attention` | Wikipedia pageviews API | ✅ | 30 | ✅ Active (replaces trends) |
| 5 | `google_trends` | pytrends (Google search volume) | ✅ | 0-18 | ⏸️ Rate-limited (429) — kept as fallback |
| 6 | `whale_13f` | SEC 13F hedge fund filings | ✅ | 0 | 🔲 SEC EDGAR browse needs cooldown |

## Registry code layout

- `app/factors/base.py` — `BaseFactor` ABC with `compute()` → `FactorResult`
- `app/factors/registry.py` — `Registry` class with `run(name)` and `run_all()`
  - Each `run()` has a 30-second timeout guard via `ThreadPoolExecutor`
  - Hung factors print `! name: timed out after 30s, skipping` and return `None`
- `scripts/run_all_factors.py` — Entry point called by 02:00 cron
  - Iterates `reg.names` with individual `try/except` per factor
  - Merges via `{ticker: mean(scores)}` over all factors that returned scores
  - Writes same `data/factor_scores_YYYYMMDD.json` format as legacy script
  - Google Trends and Whale factors that hang or return empty are gracefully skipped

## Adding a new factor

1. Create `app/factors/myfactor.py` with a class inheriting `BaseFactor`
2. Import and add to registry in `app/factors/registry.py` (both `import` line and `register_all()` call)
3. Add to `scripts/run_all_factors.py` (automatic — it uses `reg.names`)
4. Add to dashboard's Today's Data feed (`_lfeed` in `scripts/factor_dashboard.py`)
5. Run `python scripts/run_all_factors.py` to verify

## Factor implementation details

### Wikipedia factor (`app/factors/wiki.py`)
- Uses Wikimedia REST API: `/metrics/pageviews/per-article/...`
- 30 tickers in ~3 seconds — fastest factor, no API key, no rate limits
- Log-scales raw pageviews, then z-score normalizes
- Maps tickers to Wikipedia article titles via `TICKER_ARTICLES` dict
- Example: GOOGL → "Google", TSLA → "Tesla,_Inc.", AAPL → "Apple_Inc."
- Identified as the replacement for Google Trends when trends is rate-limited

### Insider factor (`app/factors/insider.py`)
- Uses SEC EDGAR daily index (free, no API key)
- Parses fixed-width format: form type at start → company → CIK → date → filename
- Filters to only CIKs in our universe (via `cik_ticker_map.json` cached from SEC's company list)
- Fetches first 4KB of each filing XML to extract `<transactionCode>` (P=Buy, S=Sell, A=Grant, M=Exercise)
- Scores: `(buys - sells) / (buys + sells)` → range -1 to +1
- Caches filings so subsequent runs only download new data
- See `references/sec-edgar-insider-factor.md` for the older standalone implementation

### Whale 13F factor (`app/factors/whale.py`)
- Uses SEC EDGAR browse-edgar for 13F-HR filings
- Name→ticker mapping built from SEC company_tickers.json (8006 entries) — cached in `data/13f_holdings/name2ticker.json`
- Normalizes company names (lowercase, strip punctuation, try common suffix removal)
- 13F XML parser extracts `<nameOfIssuer>` + `<value>` from `<infoTable>` elements
- SEC EDGAR browse-edgar endpoint returns 403 when rate-limited; needs 24h cooldown
- Filing URL format: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=13F-HR&count=5`
- Parses index page for `-index.htm` links, then finds primary document `.txt` link, then parses infoTable XML

## Dashboard integration

The "Today's Data" feed (`_lfeed` in `scripts/factor_dashboard.py`) checks all data sources:
- `_t(_last_scores(), "Factor Scores", ...)` — file at `data/factor_scores_*.json`
- `_t(Path("data/insider_trades/insider_scores.json"), "Insider SEC", ...)`
- `_t(w[-1], "Wiki Attention", ...)` — file at `data/wikipedia_views/wiki_*.json`
- Each uses `_mtime_date()` helper (returns `YYYYMMDD`) for exact date comparison against `date.today()`
- Only entries with today's date are shown

## Key : `_mtime_date()` pattern

The `_mtime_date()` helper is critical for the feed filter:
```python
def _mtime_date(p):
    if not p or not p.exists(): return None
    ts = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
    return ts.strftime("%Y%m%d")
```
Without this, checking `"20260706" in "2026-07-06 06:45 UTC"` fails because the date formats don't match.

## Troubleshooting

- **Factor returns 0 tickers**: Check if the data source is rate-limited. Google Trends returns 429, Whale 13F returns 403. Both are transient — wait 24h and retry.
- **`run_all_factors.py` hangs**: Google Trends factor's pytrends connection is hanging. The registry's 30s timeout guard catches this, but the thread still runs in the background. For immediate results, run factors individually.
- **SEC EDGAR 403 errors**: The SEC rate-limits requests. Use `time.sleep(0.5)` between requests, and cache results aggressively.