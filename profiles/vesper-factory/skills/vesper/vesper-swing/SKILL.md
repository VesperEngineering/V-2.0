---
name: vesper-swing
description: Build and run Vesper Swing — the real-time local-LLM swing trade scanner. Architecture, signal engine tuning, Ollama integration, contamination prevention.
---

# Vesper Swing

Local LLM-powered swing trade scanner running on real-time minute bars. Completely separate from Vesper's factor pipeline — different codebase, different Alpaca account, different time horizon (hours vs days).

## Architecture

```text
Massive WebSocket receiver
  → normalize + persist/dedupe minute bar
  → bounded bar queue
  → worker-thread signal engine
  → local Ollama context gate
  → fail-closed decision/execution gate
  → Alpaca paper bracket order (execution disabled during hardening)
```

The receiver must remain limited to decode, validation, durable journaling, and enqueueing. Synchronous Massive REST, Ollama, SQLite analysis writes, and Alpaca calls belong behind the queue; otherwise they starve WebSocket pings and cause reconnect gaps.

## Project layout

```
D:\swing-scope\
├── config.yaml          # Massive + Alpaca + Ollama config
├── start.bat            # Desktop launcher ("Vesper Swing.lnk")
├── venv/
├── data/                # swing_scope.db
├── logs/
└── src/
    ├── main.py          # Entry point — orchestrates the pipeline
    ├── config.py        # YAML loader
    ├── data/
    │   ├── database.py  # SQLite schema (signals, llm_analyses, trades)
    │   └── stream.py    # Massive WebSocket client with auto-reconnect
    ├── signals/
    │   └── engine.py    # 6 signal types (see below)
    ├── llm/
    │   └── analyzer.py  # Ollama API client, prompt builder, JSON parser
    ├── execution/
    │   ├── trader.py    # Fail-closed Alpaca paper execution + bracket/EOD controls
    │   └── safety.py    # Paper endpoint gate, direction map, NY EOD controller
    └── dashboard/       # Reserved; current operator surface is the console
```

## Signal engine

Six signal types, each scoring 1-10. Only signals >= min_score (config, default 7) pass to the LLM layer.

### VWAP cross (tuned — was too sensitive)

**Three gates must all pass before firing:**
1. Cross by >= 0.15% of price (no penny wiggles)
2. Previous bar was >= 0.10% away from VWAP on the other side (real cross, not hovering)
3. Volume >= 2x recent 20-bar average (institutional participation)

Works for both bullish (cross above) and bearish (cross below). Score = min(10, 4 + vol_mult + cross_pct), floored at 7.

### Gap reclaim

Stock gapped down at open vs previous close, now reclaiming.

**Requires prev_close to be seeded.** The engine calls Massive REST /v2/aggs/ticker/{T}/prev lazily on first encounter. This is cached per-ticker for the session. Without seeding, gap reclaim fires zero signals.

Score = min(10, 5 + gap_pct) — bigger gap = higher score.

### RSI extreme

RSI(14) <= 25 (oversold) or >= 75 (overbought). Score scales with extremity.

### Volume spike

Current bar volume >= 3x recent 20-bar average. Score = min(10, 5 + vol_mult).

### Bollinger squeeze

Bollinger(20, 2.0) band width narrow then price breaks out. Simplified: std < 0.5 AND close > upper band.

### Opening range break

First 15 minutes establish a range. Break above high or below low triggers. Resets each session.

## Local LLM integration

- **Model:** qwen3:14b (9.3GB, 100% GPU on RTX 5070 Ti). Switched from qwen2.5:14b for native JSON mode and thinking-mode toggle.
- **Endpoint:** http://localhost:11434 (Ollama)
- **Prompt:** System sends ticker, signal type, score, recent price action, news headlines, SEC filings. Model returns JSON: thesis, confidence (1-10), risk_factors, catalyst.
- **Temperature:** 0.3 (low - consistency over creativity)
- **Latency:** ~3-6s per call on RTX 5070 Ti
- **Gate:** LLM confidence >= min_confidence (config, default 6) to pass
- **Thinking mode:** Disabled in signal analysis (enable_thinking: False) - adds latency without benefit for structured JSON output.

## Running it

**Critical clarification: Vesper Swing's LLM (qwen3:14b local) is NOT the same as the Hermes assistant you're chatting with (DeepSeek/Claude via API).** Vesper Swing uses Ollama on localhost:11434 for signal analysis — zero cost, 100% GPU. When the user says "you" they may mean the Hermes conversation, not the signal analyzer. Be explicit about which is which.

**Prefer the batch file** — it sets PYTHONPATH and uses the correct venv, avoiding PATH contamination.

```bash
cmd /c "D:\swing-scope\start.bat"
```

From bash/zsh (Hermes terminal tool):
```bash
cd /d/swing-scope && PYTHONUNBUFFERED=1 ./venv/Scripts/python.exe -u -m src.main
```

Must use `-u` (unbuffered) or `PYTHONUNBUFFERED=1` for background sessions so logs flush to file immediately.

Desktop shortcut: Vesper Swing.lnk -> start.bat (title says "Vesper Swing", not "Swing Scope").

### PowerShell venv PATH contamination

On Windows, the Hermes venv shadows the swing-scope venv's packages. Running `python.exe -m src.main` from PowerShell fails with `ModuleNotFoundError: No module named 'yaml'` even though yaml is installed in the swing-scope venv.

**Root cause:** Hermes adds its own venv to the global PYTHONPATH environment variable. This causes ANY Python process (even inside a separate venv) to find Hermes' site-packages first instead of the local venv's packages.

**Fix options (in order of preference):**

1. Use the batch file (`start.bat`) which clears PYTHONPATH before running:
```powershell
cmd /c "D:\swing-scope\start.bat"
```

2. If the venv is already contaminated (packages installed to Hermes path instead): 
```bash
cd /d/swing-scope
rm -rf venv
PYTHONPATH="" PYTHONHOME="" python -m venv venv
PYTHONPATH="" PYTHONHOME="" ./venv/Scripts/python.exe -m pip install --no-cache-dir pyyaml requests websockets pandas sqlalchemy aiohttp
```

The `PYTHONPATH=""` prefix is essential — without it pip install writes packages to the Hermes path instead of the swing-scope venv.

Do NOT try `cd D:\swing-scope; .\venv\Scripts\python.exe -m src.main` directly from PowerShell — the import will fail with ModuleNotFoundError due to PYTHONPATH contamination.

### Handing over to the user

When the user asks to run the system themselves:
1. Stop any running background processes first.
2. Give the exact pasteable command. Prefer `cmd /c` on Windows.
3. Tell them what expected output looks like (startup banner, connecting to Massive, bars flowing).
4. Confirm it worked before moving on.
5. If imports fail, it's the venv contamination — switch to the batch file approach.

## Dependencies

- websockets, pyyaml, pandas, requests, sqlalchemy, aiohttp
- Ollama (winget install) with qwen3:14b pulled
- Massive API Advanced tier ($199/mo) for real-time WebSocket
- Separate Alpaca paper account

## Contamination prevention

Vesper Swing MUST NOT interact with Vesper's factor pipeline:

- **Separate Alpaca account** - never reuse Vesper's keys. Paper account PA3XS071DUSS.
- **Separate codebase** - D:\swing-scope\, own venv, own database.
- **Separate database** - data/swing_scope.db, never shares tables with Vesper.
- **Holdings check** - config has vesper_holdings_check: true to skip tickers Vesper holds (not yet implemented against real account).

## Signal tuning lessons

**The VWAP cross was a firehose.** First session: 2,612 VWAP signals out of 4,032 total (65%). Avg score 9.2 - useless as a filter. The original code returned a signal on ANY VWAP cross with vol_mult >= 1.5 and didn't check bearish crosses at all.
**Fix applied:** Three gates now must all pass:
1. Cross >= 0.15% of VWAP (not a penny wiggle)
2. Previous bar >= 0.10% away on the other side (real cross, not hovering)
3. Volume >= 2x recent (was 1.5x)
Bearish cross-below-VWAP also added. **Do not assume these gates solved the firehose:** the next captured session still produced 2,777 VWAP signals out of 4,488 total on `AM.*`. Treat threshold tuning as unvalidated until minute bars and forward outcomes are persisted. Use a fixed liquid watchlist, edge-trigger/cool down signals, and measure post-signal returns before expanding the universe.

**Gap reclaim was dead on arrival.** The prev_close dict was initialized empty and never populated. Zero signals all day. Fixed with lazy REST API seeding. Always test that every signal type actually fires in production.

**The LLM filter matters.** 24% of signals were rejected by the LLM (confidence < 6). SPY and JPM VWAP crosses got 4/10 confidence - the model correctly identified them as noise. Without the LLM filter, the system would flag 24% more false positives.

## Deployment hardening workflow

Vesper Swing is **collection-only until explicitly proven otherwise**. Wiring an Alpaca client is not deployment readiness.

1. Stop any running Swing process before changing execution code; back up the database and logs.
2. Ensure credentials, config, runtime data, logs, backups, and venv are ignored before initializing or staging Git. Never print or diff credential-bearing config; inspect only redacted fields.
3. Add a fail-closed execution gate. Orders require explicit `enabled: true`, `mode: paper`, and the exact Alpaca paper endpoint. Missing/unknown values reject execution.
4. Use strict RED→GREEN tests for order gating, direction semantics, EOD timing, order payloads, duplicate prevention, and failure paths.
5. Use `America/New_York` for market-session logic and trigger EOD actions once per session; never compare `15:55` directly against UTC.
6. Broker protection must be real: submit Alpaca bracket orders, then reconcile parent/child order status and actual fills. Recording stop/target values locally is not protection.
7. Map signal semantics explicitly: bullish/long/oversold→buy; bearish/short/overbought→sell; unknown/missing→reject. Never default missing direction to bullish or treat every unknown value as sell.
8. Persist raw minute bars with ticker/timestamp deduplication before signal processing. Without bars and forward-return labels, signal thresholds cannot be validated.
9. WebSocket ingestion must not await synchronous REST, Ollama, SQLite-heavy, or Alpaca work. Put slow work behind bounded queues with queue-depth, latency, reconnect, duplicate, and drop metrics.
10. Validate on a fixed liquid watchlist first, then expand to an explicit quality-controlled universe such as the current S&P 500. Never implement `sp500` as `AM.*`: load/validate 450–550 unique constituents from a free source, cache the last valid snapshot, prefix every ticker (`AM.AAPL,AM.MSFT,...`), and fail closed if live and cached lists are invalid. Add edge-triggering and per-ticker/signal cooldowns before expansion.
11. Run a bounded collect-only smoke test; verify the exact Massive subscription, zero trades, and no leftover process.
12. Require extended collection-only evidence, fault tests, reconciliation, and independent review before controlled paper execution. Live capital remains out of scope until months of paper evidence exist.
13. If the workspace cannot detect a canonical verification command, create a focused `hermes-verify-*.py` harness with Python `tempfile` under the OS temp directory, inject the project root into `sys.path` (temp scripts do not inherit it), run with the project interpreter, remove it, and report the result explicitly as ad-hoc verification rather than suite-wide proof. If the status hook still says “unverified” after successful direct execution, state the tooling-status mismatch once; do not loop through repeated equivalent harnesses or upgrade ad-hoc evidence into canonical suite evidence.
14. Enforce fail-closed checks again inside `PaperTrader.submit_trade()`. Orchestrator-only checks are bypassable; broker/API failure must be represented as unknown and reject entry, never zero positions or no loss breach. The daily-loss gate must use authoritative broker state (for example Alpaca `equity - last_equity`) or completed fill/P&L reconciliation—never treat successfully queried but stale local trade rows as authoritative.
15. Serialize entry submission, EOD flattening, and shutdown with one execution lock. Recheck EOD due-state after acquiring the lock because another worker may have flattened while waiting. Immediately before order submission, obtain a fresh clock value and call `entries_allowed()` again inside that same lock; analysis that began before cutoff must not re-enter after flattening.
16. EOD completion is two-phase: `is_due()` must not mutate state. Handle Alpaca cancel-all responses by shape: 204-style dicts and 207 arrays. Inspect every 207 item for a 2xx status, then query `GET /v2/orders?status=open` and require an empty list before closing positions. Verify flatness, reconcile local rows, then call `mark_flattened()`. Any exception, partial cancellation, surviving order, close failure, or unknown response leaves retry armed.
17. Run EOD from an independent periodic risk worker. Catch and log each risk-check exception inside the loop so one broker/API defect cannot permanently kill retries. During shutdown, stop ingress and risk work, set a runtime execution block, tolerate an already-failed risk task, discard already-journaled queued analysis, wait for in-flight `to_thread` work to return, then stop workers. Cancelling `to_thread` alone does not stop its thread.
18. Diagnose Massive close code 1008 by checking for another `D:\swing-scope\venv\Scripts\python.exe -m src.main` launched through `start.bat`. Stop only the exact process tree, then rerun a single-instance smoke test; add a durable single-instance lock before unattended operation.
19. Validate every broker-supplied numeric risk field after parsing with `math.isfinite()`. Python accepts `float("nan")` and infinities, and ordinary comparisons can silently evaluate false, bypassing cash, equity, loss, price, or sizing gates. Missing, malformed, negative-where-impossible, NaN, and ±Infinity values must become `None`/unknown and block submission before the broker POST. Parameterize regression tests across `nan`, `inf`, and `-inf`.
20. Validate broker order-creation success semantically. Require a mapping, non-empty order ID, and known accepted/pending status before persistence. Reject empty dicts, lists/207 arrays, missing IDs, empty IDs, and unknown statuses. Persist an acknowledgment as `submitted` with no entry price; the signal price belongs in audit metadata until fill reconciliation supplies actual price/time.
21. Apply finite-number validation to configuration timing too. `risk_check_interval_sec` must be a non-Boolean finite positive number; NaN/Infinity can stall `asyncio.wait_for` and silently stop future EOD retries.
22. Package a tracked, validated S&P snapshot as the final offline fallback: live free-source refresh → writable runtime cache → bundled snapshot. Validate every layer (450–550 unique syntactically valid symbols) and never fall back to `AM.*`.
23. Validate all execution-risk configuration synchronously before creating the stream or workers, and again at `run()` entry. Reject Boolean/string/non-finite/non-positive loss limits and position sizes, non-positive/non-integer position counts, and non-finite/non-positive risk intervals. Keep equivalent defensive validation at the trader boundary; configuration validation is not a substitute for boundary validation.
24. Supervise the stream, risk worker, and bar worker with first-completion semantics. If either worker exits unexpectedly, immediately stop ingress, set the runtime no-order gate, stop/cancel the stream, and preserve a contextual worker error. Shutdown must explicitly absorb/log already-failed risk *and* bar tasks so cleanup does not mask the supervisor error.
25. Treat broker submission plus local persistence as a distributed transaction. Commit a durable `submitting` intent with a deterministic `client_order_id` before POST. If broker acceptance arrives, update that row to `submitted` with no fill price. If the update fails, issue a compensating broker cancellation; retain the durable intent for restart reconciliation if cancellation is uncertain. A database failure before intent commit must make the broker POST unreachable.
26. Make failure-path tests database-safe. Stub or replace `get_db` in malformed-response tests so RED tests cannot pollute the operator database. If a test does create artifacts, identify and delete only exact test rows and verify the resulting count rather than clearing broad tables.
27. Model broker orders as an explicit state machine rather than a Boolean “accepted” result. Active states map to `submitted`; `partially_filled` and `filled` imply real exposure and map to `open`; canceled/expired/rejected states are no-exposure only when an authoritative finite `filled_qty` is exactly zero. Ambiguous transport or malformed responses remain `unknown`, never terminally rejected.
28. Make retries idempotent across processes and restarts. Persist `client_order_id` in a uniquely indexed column, use transactional get-or-create intent semantics, and reconcile an existing intent via broker lookup instead of issuing another POST. Additive SQLite migrations must work from the legacy schema and remain safe when run repeatedly.
29. Verify compensating cancellation semantically: require a successful DELETE, then either an authoritative 404 or a GET response whose order ID matches, terminal status is cancel/reject/expire, and filled quantity is exactly zero. A canceled order with any fill still represents exposure. Database `close()` failures must be logged without masking a successful commit or preventing compensation/reconciliation.
30. Apply the explicit paper-execution boundary to every broker mutation, not only entry submission. Disabled execution or a live endpoint must block EOD cancel-all, position liquidation, and compensating mutations before any API call.
31. Bind every broker response to the requested intent. Initial POST acknowledgments and lookup-by-client-ID responses must contain a `client_order_id` exactly matching the deterministic requested ID; missing or mismatched identity remains `unknown` and cannot promote local state. Order ID alone is insufficient.
32. Reject JSON booleans before numeric conversion. In Python, `float(False) == 0.0` and `float(True) == 1.0`; broker quantities, prices, balances, and configuration values must explicitly reject `bool` before `float()` or integer validation.
33. Serialize additive SQLite migration discovery and mutation. Wrap `PRAGMA table_info` → conditional `ALTER TABLE` → index creation in `BEGIN IMMEDIATE` (or an equivalent cross-process migration lock), then test two concurrent initializers against the legacy schema. Repeat-safe sequential migration does not prove concurrent safety.

Detailed hardening evidence and remaining blockers are in `references/session-2026-07-10-hardening.md`. The explicit S&P 500 loader/cache/subscription implementation is documented in `references/session-2026-07-10-sp500-universe.md`.

## Common pitfalls

### _running flag initialized to False prevents reconnect loop
The MassiveStream.__init__ sets _running = False. The run() method's while self._running is not False: loop never executes - it skips straight to the end. The program logs "Connecting to Massive WebSocket..." then exits immediately with no error.
**Fix:** Initialize _running = True in __init__. The stop() method sets it to False.

### WebSocket dies silently when additional_headers is unsupported
The websockets library version shipped with the venv may not support the additional_headers parameter on connect(). Passing it causes a silent TypeError caught by the reconnect loop.
**Fix:** Remove additional_headers=headers and move auth_msg construction inside the async with block.

### Massive auth/subscribe responses are arrays, not single objects
Massive returns [{...}] (a JSON array) even for single status events. Code expecting a dict fails on .get("status").
**Fix:** After json.loads(auth_response), check isinstance(auth_data, list) and take auth_data[0].

### Massive VWAP field is 'a', not 'vw'
In AM (Aggregate Minute) events, the VWAP field is 'a', not 'vw'. The 'vw' field is the tick's volume-weighted price, not the day's VWAP.

### Massive subscription format requires prefix per ticker
Wrong: "AM.AAPL,MSFT" -> subscribes to AM.AAPL only. Right: "AM.AAPL,AM.MSFT" - prefix each ticker individually.

### `sp500` must never alias to `AM.*`
A config label is not a universe filter. `AM.*` streams the entire market, including thin stocks, warrants, and unsuitable products. Load the current constituent table (Wikipedia is acceptable), normalize and dedupe symbols, require a plausible 450–550 count, cache the last valid snapshot, and construct explicit `AM.<ticker>` subscriptions. If both live data and cache validation fail, abort startup rather than falling back to the wildcard. Expect roughly 503 symbols because multiple share classes can make ticker count exceed 500.

### gap_reclaim silently produces zero signals
The prev_close dict is initialized empty in SignalEngine.__init__. The _check_gap_reclaim method checks self.prev_close.get(ticker) and returns None if empty. This means gap reclaim can never fire unless prev_close is seeded externally.
**Fix:** Add lazy seeding via Massive REST /v2/aggs/ticker/{T}/prev on first ticker encounter. Called once per ticker per session, cached.

### Logs don't flush to file in background mode
When running with nohup or background redirection, Python buffers stdout. logging.StreamHandler(sys.stdout) won't show up in the log file until the buffer fills.
**Fix:** Run with PYTHONUNBUFFERED=1 ./venv/Scripts/python.exe -u -m src.main for background sessions.

### qwen3 thinking mode adds latency for structured output
When using qwen3 models for signal analysis, the built-in thinking mode (chain-of-thought) runs before answering. Signal analysis only needs JSON output, not reasoning traces. This doubles latency (6s -> 12s+).
**Fix:** Set enable_thinking: False in Ollama options for signal analysis prompts. Reserve thinking mode for research/planning tasks where it adds value.

## Selecting a local model for Hermes Agent

When configuring Ollama as a custom provider in Hermes config.yaml:
```yaml
custom_providers:
  - name: ollama-local
    base_url: http://localhost:11434/v1
    api_key: no-key
```
custom_providers must be a YAML list (items prefixed with -), not a dict. A dict produces "custom_providers is a dict - it must be a YAML list" error at startup.

Launch local Hermes: hermes --model qwen3:14b

## Local model sizing

### MoE trap: total params vs active params vs VRAM
A model listed as "30B with 3.3B active" still loads ALL 30B into VRAM. The active-params optimization kicks in during generation (faster token-by-token), but the entire model file still lands in memory.
- qwen3-coder:30b is 19GB at Q4_K_M
- RTX 5070 Ti has 16GB VRAM
- Result: spills 3GB into system RAM, mixed GPU/CPU
- Still usable but first response takes 30-60s instead of 5-10s

### Hardware constraint math for 16GB VRAM
Models that fit entirely:
- qwen3:14b (9.3GB) - best daily driver, 100% GPU
- qwen2.5:14b (9GB) - predecessor, no JSON mode
- deepseek-r1:14b (9GB) - thinking mode, chain-of-thought
- phi-4:14b (9GB) - reasoning specialist

Models that spill (19GB+):
- qwen3-coder:30b (19GB) - 3GB spill, slower but usable
- gpt-oss-20B (12-14GB) - likely fits if quantization allows
- deepseek-r1:32b (20GB) - 4GB spill, slow
- gemma4:31b (20GB) - 4GB spill, strong tool calling
- qwen3.6 (24GB required per docs) - too large

### Recommended duo
- Primary: qwen3:14b (fits, fast, JSON mode) - daily driver + Vesper Swing signal analysis
- Secondary: qwen3-coder:30b (spills but fast active params) - coding sessions, use /model to switch
