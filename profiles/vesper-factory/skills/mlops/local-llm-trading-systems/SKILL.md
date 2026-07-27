---
name: local-llm-trading-systems
description: Architecture and patterns for building local LLM-powered trading systems that run alongside existing strategies — covering hardware assessment, real-time data pipelines, LLM-as-context-layer design, and contamination isolation.
category: mlops
---

# Local LLM-Powered Trading Systems

Designs for trading systems that use locally-hosted LLMs (via Ollama, llama.cpp, or similar) as a real-time context/filter layer on top of traditional quantitative signal engines. The LLM reads news, classifies regime, and connects disparate signals into a coherent trade thesis — at zero marginal token cost.

## When to use

- User wants to build a new trading strategy that leverages a local LLM for real-time analysis
- Evaluating hardware for local LLM inference (existing machine vs. dedicated box like AMD Ryzen AI Halo)
- Designing isolation between a new strategy and an existing one (e.g., Vesper + Swing Scope)
- Planning a phased build: signal engine → LLM layer → paper trade → go live
- Reviewing a **non-LLM** algo trading codebase (universe sizing, IC targets, data-source selection, free-vs-paid feeds) → see `references/reviewing-algo-trading-systems.md`

## Architecture Pattern

The realistic architecture separates concerns into layers:

```
1. DATA INGESTION (real-time)     → price/volume stream + news/SEC/social
2. TRADITIONAL SIGNAL ENGINE      → price action rules, numerical setup scores (Python, pandas, ta-lib)
3. LLM CONTEXT LAYER (local)      → sentiment, regime classification, thesis generation
4. DECISION GATE                   → signal score × LLM confidence → trade/no-trade
5. POSITION MANAGER                → entry, stop, target, time-based exit
```

**Key principle**: The LLM does NOT do price prediction. It classifies text, connects context, and filters setups the signal engine flags. Numerical pattern recognition stays in traditional code.

## What LLMs are good at in trading

- News headline classification (bullish/bearish/neutral)
- Earnings transcript summarization and tone extraction
- Connecting disparate information streams into a narrative
- Market regime classification from a basket of indicators
- Generating plain-English trade theses for auditability

## What LLMs are bad at

- Chart pattern recognition (hallucinates patterns)
- Real-time tick prediction ("will the next candle be up or down?")
- Sub-second latency trading (even 42 tok/s = 1-2s per response)
- Any task requiring precise numerical computation

## Hardware Assessment

### Existing machine check
Before recommending new hardware, check what the user already has:
```bash
# Windows (via powershell.exe from bash terminal)
powershell.exe -NoProfile -Command "Get-CimInstance Win32_Processor | Format-List Name, NumberOfCores; Get-CimInstance Win32_OperatingSystem | Format-List TotalVisibleMemorySize; Get-CimInstance Win32_VideoController | Format-List Name, AdapterRAM"
# GPU VRAM detail
powershell.exe -NoProfile -Command "nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader"
```

### VRAM → model size guide (Q4_K_M quantization)

| VRAM | Fully on GPU | Partial offload |
|---|---|---|
| 8GB | 7B models (~5GB) | 14B (~9GB, slow) |
| 12GB | 7B-9B | 14B-22B |
| 16GB | 14B (~9GB), 9B comfortably | 32B (~20GB, ~10-15 tok/s) |
| 24GB | 14B-22B | 35B-70B (slow) |
| 64GB+ unified (Halo/Mac) | 35B MoE (~20GB) | 122B MoE (~76GB, ~8 tok/s) |

### Unified memory vs discrete VRAM
- **Discrete GPU (NVIDIA CUDA)**: Most turnkey. Ollama auto-detects, CUDA built-in. Limited by VRAM size.
- **AMD unified memory (Ryzen AI Max+ 395)**: 128GB pool, up to 112GB GPU-accessible. Runs 70B-122B models. ROCm required (mature on Linux, limited on Windows). No discrete GPU upgrade path.
- **Bandwidth matters**: 256 GB/s (Halo) vs 1,008 GB/s (RTX 4090) vs 3,350 GB/s (H100). Higher bandwidth = faster token generation.

### Ollama install
```bash
# Windows
winget install Ollama.Ollama
# Or direct installer from ollama.com

# Pull and run
ollama pull qwen2.5:14b
ollama run qwen2.5:14b

# Verify GPU offload
ollama ps  # should show "100% GPU" or partial
```

## Hermes Local-Agent Integration

For a Windows Ollama model to serve as a **Hermes tool-using agent**, validate its advertised context window first: Hermes requires at least 64K. Keep a separate local profile rather than replacing the user's cloud default, remove cloud fallback when the worker must remain local/fail-closed, and verify an actual harmless tool call before declaring it ready. See `references/hermes-local-ollama-profile.md` for the verified Windows/Ollama profile workflow, context-window trap, and resource envelope.

When explaining this workflow to the user, give the immediate numbered commands first; avoid API/integration tangents unless they ask for them.

## Data Pipeline (Massive API)

User is on Massive Advanced ($199/mo): real-time WebSockets, unlimited calls.

| Endpoint | Use | Access |
|---|---|---|
| `wss://socket.massive.com/stocks` | Real-time minute aggregates (`AM.*`) | Advanced only |
| Second aggregates | Finer granularity if needed | Starter+ |
| Trades + Quotes | Level 1 bid/ask | Advanced only |
| REST historical | 20yr minute bars for backtesting | Advanced |

**Critical**: Only Advanced ($199/mo) is real-time. Starter ($29) and Developer ($79) are 15-minute delayed — unusable for intraday swing trading.

**News data**: Benzinga real-time news is a Massive add-on at $99/mo. Free alternatives for paper trading phase: RSS feeds, SEC EDGAR real-time, Reddit API (rate-limited but free).

## Contamination Isolation (Multi-Strategy)

When running two strategies (e.g., Vesper overnight + Swing Scope intraday), isolation is non-negotiable:

### Three contamination vectors

1. **Position contamination** — strategies take opposing positions on the same ticker
   - Fix: **Separate Alpaca accounts**. Never share an account between strategies.

2. **Code contamination** — shared codebase means a bug in one breaks both
   - Fix: **Separate repos, separate venvs, separate databases**. The only shared thing is the dashboard frontend (separate page/tab).

3. **Capital contamination** — one strategy starves the other's capital
   - Fix: **Separate capital allocation**. Vesper keeps its $106K, Swing Scope gets its own $3-5K. Separate accounts solves this automatically.

### Design rule
> Separate accounts, separate codebases, separate databases, separate capital. The only shared thing is the dashboard view. Zero crossover.

## Strategy Comparison (for context)

| Dimension | Factor-based (Vesper) | LLM-augmented swing |
|---|---|---|
| Horizon | Days to weeks | Hours to days |
| Positions | Overnight holds | Flat by EOD or 1-3 day |
| Signal source | Daily factor scores | Real-time price action + news |
| Execution | Scheduled rebalance | Intraday, setup-triggered |
| AI role | Offline factor research | Real-time context filtering |
| Account | Dedicated | Separate dedicated |
| Edge basis | Academic factor literature | Price action + LLM context layer |

## Phased Build Approach

**Phase 1 — Signal engine only, no LLM (2-3 weeks)**
- Python scanner on minute bars (Massive real-time WS)
- Detect: gap reclaims, VWAP crosses, volume spikes, RSI extremes
- Log every signal to CSV/dashboard, no trading

**Phase 2 — Add LLM context layer (1-2 weeks)**
- Install Ollama, pull model appropriate for VRAM
- When signal fires: feed LLM the ticker, setup type, recent news, sector context
- LLM returns: thesis, confidence (1-10), risk factors
- Log LLM calls alongside signals — start calibration dataset

**Phase 3 — Paper trade combined signal (2-3 months)**
- Signal score × LLM confidence → trade decision
- Execute in separate Alpaca paper account
- Track: win rate, avg win/loss, LLM confidence vs actual success correlation
- This is where you discover if the LLM adds alpha or just adds confidence

**Phase 4 — Go live with small size**
- $3K, fractional shares, tight risk controls
- Only after paper data shows edge

## Position-Manager Risk Controls

Before wiring stops, time exits, or crash breakers into a broker or scheduler, build a pure broker-free simulator and validate conservative fill semantics. Decisions made at a close execute no earlier than the next tradable open; gaps through stops fill at the gap open; and when multiple downside thresholds overlap, the highest threshold triggers first. Keep early-exit capital in cash until the real strategy would rebalance, and evaluate daily marked-to-market drawdown rather than rebalance points alone. **Fail closed before performance calculation** unless prices are split-adjusted, membership and required classifications are point-in-time, and every signal query enforces its historical cutoff. Broker deployment must reconcile confirmed fills, partial/fractional quantities, protective-order state, restarts, and concurrent rebalances idempotently through one serialized controller.

See `references/risk-control-validation.md` for the full validation sequence, historical-test contract, and production deployment gates.

## Key Pitfalls

1. **LLM confidence calibration is unsolved.** The model will sound convincing and be wrong 40% of the time. You need hundreds of forward-tested setups before trusting it for auto-execution. Never skip the calibration phase.

2. **15-minute delayed data is unusable for intraday.** Only Massive Advanced ($199/mo) is real-time. Verify the tier before building.

3. **Don't use the LLM for price prediction.** It will hallucinate chart patterns. Price action detection stays in traditional code (pandas, ta-lib). The LLM is a text/context layer only.

4. **Backtesting the LLM layer is impossible.** You can backtest the signal engine on historical data, but "what would the LLM have said on March 15 at 10am?" can't be answered — you don't have the archived news stream, and the model wasn't running. Forward paper trading is the only validation path.

5. **Splitting attention before existing strategy is proven.** If an existing strategy (Vesper) hasn't gone live yet, building a second system divides focus. Recommend: existing strategy live first, then build the new one.

6. **ROCm on iGPU is less turnkey than CUDA.** AMD's software stack is improving but expect configuration friction on Linux. On Windows, ROCm support is limited. NVIDIA + Ollama is the path of least resistance.

7. **No discrete GPU upgrade path on unified-memory boxes.** The AMD Halo's iGPU is what you get. Can't add a 4090 later. Plan model size around fixed hardware.

8. **Massive WebSocket silent failure modes.** Several subtle bugs can cause the stream to appear to connect but silently produce no data: (a) `_running = False` in init creates a `while` loop that never enters — the app starts, prints "Connecting...", and exits with zero errors; (b) auth responses come as JSON arrays, not objects — must unwrap `[0]` before checking status; (c) the VWAP field in AM events is `a`, not `vw`; (d) watchlist subscriptions must be `"AM.AAPL,AM.MSFT"` not `"AM.AAPL,MSFT"`; (e) newer `websockets` library (14.x+) removed `additional_headers` — omit it entirely. Full debugging session documented in `references/massive-websocket-debugging.md`.

9. **Log buffering on Windows background processes.** Python stdout/stderr buffering means log lines after connection may never appear in files. Use `PYTHONUNBUFFERED=1` and `python -u` flags to force flush, or logs will show "Connecting..." and nothing else — indistinguishable from a silent crash. **This is a hard requirement — do not run without it.** Launch command: `PYTHONUNBUFFERED=1 python -u -m src.main`. Without unbuffered output, diagnostic log lines (auth success, subscription confirmation, first bar received) are stuck in a buffer and the process appears dead when it's actually healthy.

10. **Universe subscriptions must match the strategy mandate.** Use `AM.*` only when the strategy explicitly requires the entire active US market and downstream throughput has been proven. For an S&P 500 mandate, subscribe to explicit `AM.<ticker>` symbols from a validated constituent source. A bounded per-ticker buffer controls memory but does not control database writes, signal volume, LLM demand, or queue saturation.

11. **Qwen3 thinking mode can silently consume the response budget.** Current Ollama expects top-level `"think": false`; nesting `enable_thinking` under `options` may be ignored, producing long inference, hidden reasoning, empty visible responses, parse failures, and downstream queue overflow. Measure the exact production payload before increasing queues or adding concurrency. See `references/ollama-throughput-debugging.md`.

## Project Implementation (Phase 0-1 Built, Live as of July 9 2026)

Phase 0-1 is complete — Ollama installed, qwen2.5:14b pulled, 100% GPU offload verified on RTX 5070 Ti. Full project built at `D:\\swing-scope\\` with signal engine (6 signals, VWAP tuned), LLM analyzer, Massive WebSocket stream, and SQLite database. **Running live** — `AM.*` subscribes to all US stocks (NASDAQ + NYSE + everything). Renamed to **Vesper Swing** (desktop shortcut, window title, batch file). Launches via `D:\\swing-scope\\start.bat` or the `Vesper Swing` desktop icon.

**First session stats (July 9 2026, afternoon session):** 4,032 signals fired, 4,031 LLM analyses run (~3.5s avg latency), average LLM confidence 6.6/10, 24% filter rate. VWAP cross was initially 65% of all signals (overly sensitive). Tuned in-session with 3 gate thresholds — expected to drop VWAP signal count by 90%+.

**Recommended model upgrade**: `qwen3:14b` over `qwen2.5:14b` — same ~9GB footprint, same 100% GPU offload on 16GB VRAM, but with native JSON mode (eliminates markdown code block parsing workaround) and toggle-able chain-of-thought thinking mode. 83% MMLU vs qwen2.5's ~79%. Better for the structured JSON output the LLM context layer requires. Pull with `ollama pull qwen3:14b`.

For the actual built project structure, database schema, signal scoring logic, and LLM prompt/parsing details, see `references/swing-scope-project-structure.md`.

To start a new swing-scope project from this template, copy `templates/config.yaml` and fill in API keys.

## Signal Tuning Methodology

### VWAP Cross — 3-gate approach

The VWAP cross is the most common signal but also the noisiest. Without tuning, it fires on every stock that crosses its average price every minute — 2,612 signals in one afternoon session. The tuned version adds three gates:

1. **Meaningful price move**: cross must exceed VWAP by at least 0.15% (not a penny wiggle)
2. **Real cross, not hovering**: previous bar must be at least 0.10% on the other side of VWAP
3. **Volume confirmation**: current bar volume must be at least 2x the 20-period average

Score formula: `min(10, int(4 + volume_mult + cross_pct))` with floor at 7 once all gates pass. Also handles both directions (bullish cross above, bearish cross below) — the original only caught bullish crosses.

### Gap Reclaim — Lazy prev_close seeding

Gap reclaim requires the previous day's closing price, which is not available from real-time WebSocket bars. Solution: lazy-seed via Massive REST `/v2/aggs/ticker/{ticker}/prev` on first encounter of a ticker. Results cached in `self.prev_close` dict. Tag `_seeded` set to prevent repeat API calls.

## References
- `references/team-skill-deployment.md` — Deploying skills across Hermes profiles for multi-agent trading system teams (profile inventory, role-to-skill mapping, hub-install workaround, verification)
- `references/massive-api-tiers.md` — Massive API plan comparison, WebSocket endpoints, data access by tier
- `references/massive-websocket-debugging.md` — Debugging session: auth response shapes, field names, subscription format, silent exit bugs, Windows log flushing
- `references/hardware-benchmarks.md` — Local LLM benchmarks on various hardware (RTX 5070 Ti, Ryzen AI Max+ 395 Halo, Mac Studio)
- `references/swing-scope-architecture.md` — Detailed architecture for the Swing Scope concept (signal engine + LLM context layer)
- `references/swing-scope-project-structure.md` — Built project tree, database schema, signal scoring logic, LLM prompt/parsing, what's implemented vs stubbed
- `references/neural-representation-sandbox.md` — Isolation, continuous-compute, observability, and latent-interpretation protocol for JEPA/self-supervised neural research beside a production trading system
- `references/risk-control-validation.md` — Broker-free stop/time/crash-control validation, conservative daily-bar fills, backtest contract, and production reconciliation gates
- `references/ollama-throughput-debugging.md` — Diagnose Qwen/Ollama thinking-mode stalls, queue saturation, exact-payload probes, and safe live verification
- `references/reviewing-algo-trading-systems.md` — Review checklist for non-LLM algo trading codebases: config/code contract, IC targets, universe sizing, free-vs-paid data tiers, phased build plan, red flags
- `templates/config.yaml` — Starter config for a swing-scope project (Massive, Alpaca, Ollama, signals, risk)
