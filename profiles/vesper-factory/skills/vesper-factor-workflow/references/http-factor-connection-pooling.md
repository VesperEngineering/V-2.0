# HTTP Factor Connection Pooling Recipe

Reusable pattern for HTTP-based factors that need to make 500–1000+ API calls
in <10s. Proven on `wiki_attention` (502 tickers, 1004 calls) — reduced runtime
from 23s to 1.5s.

## Core principle

The bottleneck in high-volume HTTP factors is almost always **per-call TCP/TLS
handshake overhead**, not bandwidth. `urllib.request.urlopen()` opens a fresh
TCP connection + TLS handshake for every call, costing 200–800ms per request.
A `requests.Session` with connection pooling reuses connections, eliminating
this overhead entirely.

## Recipe

```python
import threading
import requests

HEADERS = {"User-Agent": "..."}

def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=20,
        pool_maxsize=20,
        max_retries=0,
    )
    s.mount("https://", adapter)
    return s

_tls = threading.local()

def _get_session() -> requests.Session:
    if not hasattr(_tls, "session"):
        _tls.session = _make_session()
    return _tls.session
```

## Concurrency control

Wikipedia CDN has a per-IP connection limit. 100 workers × 1 call each floods
the edge and triggers connection throttling → half the calls timeout. A
`threading.BoundedSemaphore` caps active connections:

```python
_CONCURRENT_LIMIT = threading.BoundedSemaphore(35)

def _http_get_json(url, timeout=4.0):
    session = _get_session()
    with _CONCURRENT_LIMIT:
        for attempt in range(3):
            try:
                resp = session.get(url, timeout=timeout)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 429:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                ...
```

Tune the semaphore: start at 25, test for failures. If >5% fail, reduce. If
it's fast with 0 failures, increase. 35 is the sweet spot for Wikipedia.

## Cold-start DNS warmup

First run in a fresh process has OS-level DNS resolution + TLS establishment
cost for the first batch. Fix with a parallel pre-flight:

```python
from concurrent.futures import ThreadPoolExecutor

def _warmup_connections():
    def _warm(url):
        try:
            s = _make_session()
            s.head(url, timeout=(3, 3))
            s.close()
        except Exception:
            pass
    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(_warm, "https://en.wikipedia.org/api/rest_v1/")
            f2 = ex.submit(_warm, "https://wikimedia.org/api/rest_v1/")
            f1.result(timeout=4)
            f2.result(timeout=4)
    except Exception:
        pass
```

This cuts cold-start from ~13s to <3s. Fire-and-forget — failures are ignored.

Call `_warmup_connections()` right before the pool submission block in
`fetch_all_features()`.

## Flat task pool

Pageviews and summaries are submitted as **independent tasks** to one pool,
not as sequential pairs inside each worker:

```python
with ThreadPoolExecutor(max_workers=50) as ex:
    futs_pv = {ex.submit(_fetch_pageviews, t, a, s, e): t for t, a in jobs}
    futs_summ = {ex.submit(_fetch_summary, t, a): t for t, a in jobs}
    all_futs = {**futs_pv, **futs_summ}
    for fut in as_completed(all_futs):
        ticker, data = fut.result()
        ...
```

This turns 500 serial-pair tasks into 1000 independent tasks, maximizing
concurrency. With 50 workers and 25 concurrent semaphore slots, the pool
always has work queued behind the semaphore.

## Performance

| Approach | Workers | Time (502 tickers) | Failures |
|----------|---------|-------------------|----------|
| urllib, serial pairs | 8 | 23s+ | high |
| urllib, flat pool | 100 | 13.4s | moderate |
| requests.Session, flat pool | 100 | 1.8s | 1 |
| requests.Session + semaphore(35) + warmup | 50 | **1.5s** | 1 |

## Pitfalls

- **`requests.Session` is NOT thread-safe.** Use thread-local storage.
- **`timeout=5` is ambiguous.** For cold DNS, use `timeout=(connect, read)`
  tuple — `timeout=(3,3)` means 3s connect, 3s read.
- **Semaphore too large → connection throttling.** Symptoms: 50+ summary
  failures on cold start, runtime spikes to 18s. Reduce semaphore, retest.
- **Don't use `.sh` for cron wrappers** (Windows path-mangling bug). Use `.py`.
- **Always `quote(article, safe='')`** for Wikipedia article names with special
  characters (e.g., `&` in `Johnson_&_Johnson`).
