# Wikipedia Attention Factor (v2 — pageviews + text sentiment)

Retail attention signal combining three sub-scores from Wikipedia REST API
(free, no API key, no rate limits on the `/page/summary/` and `/pageviews/`
endpoints).

## Architecture

```
wiki_attention score = 0.45 × pageview_zscore
                     + 0.25 × text_length_zscore
                     + 0.30 × sentiment_zscore
```

### Sub-score 1: Pageviews (45%)
7-day total pageview count from Wikimedia REST API, log-scaled and z-scored
cross-sectionally. High pageviews = high retail attention.

### Sub-score 2: Text length (25%)
Character count of the Wikipedia article summary extract (`extract` field
from `/page/summary/`), log-scaled and z-scored. Longer summaries = more
coverage = more institutional interest / notability.

### Sub-score 3: Sentiment (30%)
Keyword extraction from the article summary text. Count of risk keywords
(minus) vs growth keywords (plus), z-scored.

**Risk keywords**: lawsuit, investigation, recall, bankruptcy, SEC, fine,
settlement, penalty, fraud

**Growth keywords**: expansion, acquisition, launch, breakthrough, record,
growth, surge

Sentiment score = growth_count − risk_count. Positive = growth-heavy
article text. Negative = risk/legal-heavy.

## API endpoints

1. Pageviews: `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/{article}/daily/{start}/{end}`
2. Summary: `https://en.wikipedia.org/api/rest_v1/page/summary/{article}`

Both are free, no API key. The summary endpoint returns `{title, extract,
description, ...}` — the `extract` field is plain text, typically 500–3000 chars.

## HTTP optimization

Uses `requests.Session` with connection pooling (thread-local), a 35-slot
concurrency semaphore, and a parallel DNS/TLS warmup before the fetch burst.
Full recipe: `references/http-factor-connection-pooling.md`.

## Performance

| Metric | Value |
|--------|-------|
| Tickers scored | 501/502 |
| API calls | 1,004 (2 per ticker) |
| Warm runtime | **1.3–1.8s** |
| Cold runtime (first process) | 1.5–3s (with warmup) |
| Workers | 50 |
| Concurrent limit | 35 (semaphore) |
| Per-call timeout | 4s |

## Ticker → Article mapping

502 entries from `data/wiki_article_map.json`, built by
`scripts/build_wiki_article_map.py` from the Wikipedia S&P 500 constituents
list. Fallback: 30 hardcoded mega-cap tickers.

## Output

Saves to `data/wikipedia_views/wiki_YYYYMMDD.json`:
```json
{
  "source": "wikipedia",
  "date": "2026-07-08",
  "scores": {"AAPL": 0.5123, "MSFT": 0.8912, ...},
  "metadata": {
    "status": "SUCCESS",
    "scored": 501,
    "pageviews_scored": 501,
    "text_scored": 501,
    "sentiment_scored": 501,
    "fetch_seconds": 1.42,
    "workers": 50
  }
}
```

## Command-line usage

```bash
# Full run
python app/factors/wiki.py

# Limit to 20 tickers for quick test
python app/factors/wiki.py --limit 20

# Custom worker count, top 5 display
python app/factors/wiki.py --workers 80 --top 5
```

## Registry integration

```python
from app.factors.registry import get_registry
r = get_registry()
result = r.run('wiki_attention')
print(f"Scored {len(result.scores)} tickers in {result.metadata['total_seconds']}s")
```
