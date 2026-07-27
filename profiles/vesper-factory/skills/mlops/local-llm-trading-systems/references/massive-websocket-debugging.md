# Massive WebSocket Integration — Debugging Session

Date: 2026-07-09 | Hardware: RTX 5070 Ti (16GB), Windows 11 | Python 3.11

## Working subscription format

Massive AM events use comma-separated ticker+channel pairs. Each pair is `CHANNEL.TICKER`:

```python
# Correct — each ticker gets its own channel prefix
params = "AM.AAPL,AM.MSFT,AM.NVDA,AM.TSLA"
# Wrong — single channel prefix with comma-separated tickers
params = "AM.AAPL,MSFT,NVDA,TSLA"

# Build programmatically:
params = ",".join(f"AM.{t}" for t in watchlist)
```

## Auth response shape

Massive returns auth responses as **arrays of objects**, not single objects:

```python
# What Massive sends: [{"ev":"status","status":"connected","message":"Connected Successfully"}]
# What naive code expects: {"ev":"status","status":"connected","message":"Connected Successfully"}

auth_data = json.loads(auth_response)
if isinstance(auth_data, list):
    auth_data = auth_data[0]  # unwrap
```

## VWAP field name

In AM (Aggregate per Minute) events, the VWAP field is **`a`**, not `vw`. The docs show `a` as "Today's volume weighted average price" — it's the running VWAP for the day.

```python
vwap = bar.get("a") or bar.get("vw")  # 'a' is the correct field
```

## Silent exit bug: `_running = False` in init

**This was the critical showstopper.** The `MassiveStream.__init__` set `self._running = False`, and the `run()` method had:

```python
async def run(self):
    while self._running is not False:  # False is not False → False → NEVER ENTERS
        await self._connect()
```

Python truthiness: `False is not False` evaluates to `False`. The while loop body never executed. The process connected to the WebSocket, started, and immediately returned with zero output after "Connecting..." — exactly what we saw.

**Fix**: Initialize `self._running = True`. Only set to `False` in `stop()`.

## `additional_headers` parameter removal

Newer versions of the `websockets` library (14.x+) removed the `additional_headers` parameter from `websockets.connect()`. If used, it raises a `TypeError: unexpected keyword argument`. The fix is to simply omit it — Massive's WebSocket auth is done via the JSON `auth` action message, not HTTP headers.

```python
# Working for websockets >= 14.x:
async with websockets.connect(url, ping_interval=20, ping_timeout=60) as ws:
    pass
```

## Log flushing on Windows

Python's stdout/stderr buffering on Windows (especially in nohup/background contexts) means log lines may never appear in files. Two fixes:

```bash
# Option A: Environment variable
PYTHONUNBUFFERED=1 python -u -m src.main

# Option B: Force flush in logging config
logging.basicConfig(handlers=[logging.StreamHandler(sys.stdout)], ...)
```

Without unbuffered output, the "Connecting to Massive WebSocket..." line appeared but nothing after it — because the subsequent log lines were stuck in a buffer that never flushed before the process exited.

## Verified working connection test

This snippet was used to verify the full pipeline — auth, subscribe, and data reception — in isolation before debugging the main app:

```python
import asyncio, websockets, json, time

async def test():
    async with websockets.connect("wss://socket.massive.com/stocks", 
                                   ping_interval=20, ping_timeout=60) as ws:
        # Auth
        await ws.send(json.dumps({"action": "auth", "params": API_KEY}))
        await ws.recv()
        
        # Subscribe
        await ws.send(json.dumps({"action": "subscribe", 
                                   "params": "T.AAPL,T.NVDA,T.TSLA,AM.AAPL,AM.NVDA,AM.TSLA"}))
        
        # Read bars — they arrive at the end of each minute
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=75)
            # Process bars...

asyncio.run(test())
```

On the RTX 5070 Ti test machine, this received 17,670 trades and 6 minute bars in 75 seconds during market hours, confirming the API key, WebSocket endpoint, and data flow all work.
