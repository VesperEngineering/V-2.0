---
name: massive-websocket-stream
description: Connect to Massive API WebSocket for real-time stock data — auth, subscribe, handle events, common pitfalls.
---

# Massive WebSocket Stream

Real-time stock market data via Massive WebSocket API. Used by Swing Scope for minute-bar streaming.

## Quick connect test (Python)

```python
import asyncio, websockets, json

async def test():
    api_key = "YOUR_KEY"
    async with websockets.connect("wss://socket.massive.com/stocks", ping_interval=20, ping_timeout=60) as ws:
        # Auth
        await ws.send(json.dumps({"action": "auth", "params": api_key}))
        resp = json.loads(await ws.recv())
        # NB: Massive sends ARRAYS of status objects — index [0] first
        if isinstance(resp, list): resp = resp[0]
        assert resp["status"] != "error", f"Auth failed: {resp}"

        # Subscribe — format: "AM.AAPL,AM.MSFT" (prefix each ticker)
        await ws.send(json.dumps({"action": "subscribe", "params": "AM.AAPL,AM.MSFT,AM.NVDA"}))

        # Stream
        async for msg in ws:
            data = json.loads(msg)
            if isinstance(data, list):
                for event in data:
                    if event.get("ev") == "AM":
                        print(f"{event['sym']} O={event['o']} C={event['c']} V={event['v']}")
```

## Common pitfalls

1. **Auth/subscribe responses are arrays, not objects.** Always check `isinstance(data, list)` and index `[0]` before accessing `.get("status")`.

2. **Subscribe parameter format:** Must be comma-separated with prefix: `"AM.AAPL,AM.MSFT"` — NOT `"AM.AAPL,MSFT"` and NOT `"AAPL,MSFT"`. Each ticker needs its own event-type prefix.

3. **VWAP field in AM events:** The VWAP is in the `"a"` field (accumulated VWAP for the day), not `"vw"`. See: `event["a"]`.

4. **Bars fire at minute boundaries.** An `AM` event is emitted when the minute closes. Subscribe and wait — the first bar arrives at the next minute boundary (up to 60s wait).

5. **`_running` flag pattern:** If using a reconnect loop with `while self._running is not False:`, initialize `self._running = True` in `__init__`. Otherwise the loop never executes.

6. **`additional_headers` not supported** in newer websockets library versions — omit it, use the plain `websockets.connect(url)` call.

7. **A named universe must not alias to a wildcard.** If configuration says `sp500`, load and validate the actual constituent list (roughly 450–550 unique symbols), cache the last valid snapshot, and subscribe explicitly as `AM.AAPL,AM.MSFT,...`. If live and cached universe sources are invalid, abort startup rather than silently using `AM.*`.

8. **Close code 1008 can mean a competing connection.** Before treating it as bad auth or malformed subscriptions, inspect for another process using the same Massive entitlement. Stop only the exact duplicate process tree, rerun one clean connection, and use a cross-process single-instance lock for unattended services.

9. **Keep the socket reader lightweight.** Decode, validate, durably journal/dedupe, and enqueue. Move blocking SQLite, REST, LLM, and trading work to threads/workers behind a genuinely bounded queue. On overload, preserve the durable bar and explicitly skip stale analysis rather than blocking pings or growing memory without bound.

10. **Reconnect health must be explicit.** Grow backoff after failures; reset it only after successful auth/subscription setup or valid market data. Test auth failure, immediate disconnect, valid-event reset, and replay deduplication separately.

11. **Validate safety-critical configuration synchronously before opening the socket.** Reject booleans, missing values, zero/negative values, and non-finite floats (`NaN`, `+Inf`, `-Inf`) for queue sizes, worker intervals, and trading-risk limits. Validation inside a background task is too late: the stream can continue after that task dies.

12. **Supervise critical workers with the stream.** Await stream, persistence/analysis worker, and risk worker with first-completion semantics. If a critical worker exits unexpectedly, immediately stop ingress, close/cancel the stream, gate execution, drain or discard already-journaled work deliberately, and propagate the failure. Never discover a dead risk worker only during shutdown.

See `references/fail-closed-stream-pipeline.md` for reusable validation, supervision, overload, and verification patterns.

## Real-time vs Delayed

| Tier | URL |
|---|---|
| Real-time (Advanced, $199/mo) | `wss://socket.massive.com/stocks` |
| 15-min delayed (Starter/Dev) | `wss://delayed.massive.com/stocks` |

## Available event types

| Prefix | Description |
|---|---|
| `AM` | Aggregate per minute (OHLCV) |
| `A` | Aggregate per second (OHLCV) |
| `T` | Trades (price, size, exchange) |
| `Q` | Quotes (bid/ask) |
