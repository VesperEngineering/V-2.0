# Live Alpaca Portfolio Endpoint

Added 2026-07-07, rewired 2026-07-09. Provides real-time portfolio equity, P&L, and positions
directly from the Alpaca API, bypassing the daily snapshot files.

## Server endpoint: `/api/portfolio-live`

Server-side in `server.py` — 5s in-memory cache to avoid hammering Alpaca on every browser poll.

```python
_ALPACA_CLIENT = None
_ALPACA_CACHE = {}
_ALPACA_LAST_FETCH = 0

def _get_alpaca_portfolio():
    """Fetch live portfolio from Alpaca paper trading, cached 5s."""
    global _ALPACA_CLIENT, _ALPACA_CACHE, _ALPACA_LAST_FETCH
    now = __import__('time').time()
    if now - _ALPACA_LAST_FETCH < 5 and _ALPACA_CACHE:
        return _ALPACA_CACHE
    try:
        import dotenv
        from alpaca.trading.client import TradingClient
        env_path = VESPER_ROOT / ".env"
        dotenv.load_dotenv(env_path)
        key = os.getenv("ALPACA_KEY_ID")
        secret = os.getenv("ALPACA_SECRET_KEY")
        if _ALPACA_CLIENT is None:
            _ALPACA_CLIENT = TradingClient(key, secret, paper=True)
        acct = _ALPACA_CLIENT.get_account()
        positions = _ALPACA_CLIENT.get_all_positions()
        active = [
            {"ticker": p.symbol, "qty": float(p.qty),
             "market_value": round(float(p.market_value), 2),
             "cost_basis": round(float(p.cost_basis), 2) if p.cost_basis else 0,
             "unrealized_pl": round(float(p.unrealized_pl), 2),
             "unrealized_pl_pct": round(float(p.unrealized_plpc), 4)}
            for p in positions if float(p.market_value) > 1
        ]
        _ALPACA_CACHE = {
            "equity": round(float(acct.equity), 2),
            "cash": round(float(acct.cash), 2),
            "buying_power": round(float(acct.buying_power), 2),
            "positions": active,
            "position_count": len(active),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _ALPACA_LAST_FETCH = now
        return _ALPACA_CACHE
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}
```

## JS polling

In `data-binder.js`, `restartRefreshTimer()`:

```js
// Live portfolio poll — updates P&L directly from Alpaca every 10s
setInterval(function() {
  fetch("/api/portfolio-live").then(function(r){return r.json()}).then(function(live){
    if (live.equity) renderPortfolioLive(live);
  }).catch(function(){});
}, 10000);
```

## Refresh cadence (market hours)

| Component | Frequency | Source |
|-----------|-----------|--------|
| Market clock + status | 1s | Browser JS |
| "Updated Xs ago" counter | 1s | Browser JS |
| Aggregator trigger | 5s | `POST /api/refresh` (0.1s runtime) |
| **Live portfolio P&L** | **10s** | **`GET /api/portfolio-live`** (5s server cache) |
| Portfolio snapshot to disk | 1min | `alpaca_portfolio.py` (market hours, cron `* 9-16 * * 1-5`) |

## Pitfalls

- **Alpaca rate limits**: 5s server cache prevents hitting Alpaca on every browser poll. 10s browser poll × 5s cache = ~12 Alpaca calls/min — well within 200/min limit.
- **Server restart required**: Adding new endpoints requires killing the old server (`taskkill /F /PID <pid>`) and restarting `server.py`.
- **Negative cash**: Paper trading accounts show negative cash (margin) which is normal. Display as-is.
- **Auto-start**: `vesper-dashboard.bat` in `shell:startup` launches `server.py` via `pythonw.exe` from the Hermes venv.
