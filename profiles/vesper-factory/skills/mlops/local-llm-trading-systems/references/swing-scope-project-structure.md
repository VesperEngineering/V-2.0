# Vesper Swing — Built Project Structure (Phase 0-1 Live, July 9 2026)

**Project name**: Vesper Swing (formerly Swing Scope — renamed to distinguish from Vesper main)
**Desktop shortcut**: `Vesper Swing.lnk` → `D:\swing-scope\start.bat`
**Location**: `D:\swing-scope\` — completely separate from Vesper (`D:\vesper\`)

Starting command: `PYTHONUNBUFFERED=1 ./venv/Scripts/python.exe -u -m src.main`

## Installed Components

### Ollama (verified July 9 2026)
- Version: 0.31.2 (`winget install Ollama.Ollama`)
- Current model: `qwen2.5:14b` (9GB Q4_K_M, 100% GPU on RTX 5070 Ti 16GB)
- **Recommended upgrade**: `qwen3:14b` — same 9GB, native JSON mode + thinking mode, 83% MMLU. Better structured output eliminates markdown code block parsing workarounds. `ollama pull qwen3:14b`
- API at `http://localhost:11434`

### Live Data (verified July 9 2026)
- Universe: `all` — `AM.*` wildcard, all US exchanges
- Throughput: 17,670 trades + 6 bars across 3 tickers in 75s (direct test); ~3,800+ bars/min full AM.*
- Latency: 3-4s from signal trigger to LLM verdict (local GPU, zero token cost)

### Session Metrics (July 9 2026 afternoon)
- **4,032 signals**, 4,031 LLM analyses (3.5s avg), confidence avg 6.6 (range 2-9)
- **3,057 would have traded (76%)**, 974 rejected by LLM (24% filter rate)
- Signal breakdown: VWAP cross 2,612 (65% — tuned mid-session), RSI extreme 901 (22%), OR break 300, Volume spike 147, Bollinger squeeze 72
- Gap reclaim: 0 — prev_close dict was never populated (fixed mid-session with lazy REST seeding)

### Python Environment
- venv at `D:\swing-scope\venv\` (Python 3.11.15)
- Installed: websockets, pyyaml, pandas, requests, sqlalchemy, aiohttp

## Project Tree

```
D:\swing-scope\
├── config.yaml              # API keys, signal params, risk rules — EDIT THIS
├── start.bat                # desktop-launchable: title Vesper Swing
├── status.bat               # quick status check (Ollama models + running state)
├── venv/                    # isolated Python environment
├── data/                    # SQLite database (swing_scope.db, auto-created)
├── logs/                    # swing_scope.log
└── src/
    ├── __init__.py
    ├── main.py              # entry point: PYTHONUNBUFFERED=1 python -u -m src.main
    ├── config.py            # YAML config loader (cached)
    ├── data/
    │   ├── __init__.py
    │   ├── database.py      # SQLite schema: minute_bars, signals, llm_analyses, trades
    │   └── stream.py        # Massive WebSocket client (AM.* minute aggregates)
    ├── signals/
    │   ├── __init__.py
    │   └── engine.py        # 6 signal types, BarBuffer, signal scoring (1-10)
    ├── llm/
    │   ├── __init__.py
    │   └── analyzer.py      # Ollama API client, prompt builder, JSON parser, ContextGatherer
    ├── execution/           # Phase 3 — Alpaca paper trading (empty)
    └── dashboard/           # Phase 3 — dashboard page (empty)
```

## Database Schema (SQLite)

4 tables, all in `data/swing_scope.db`:

- **minute_bars**: ticker, timestamp, OHLC, volume, vwap, accumulated_volume
- **signals**: ticker, timestamp, signal_type, signal_score (1-10), price, volume, vwap, rsi, context_json
- **llm_analyses**: signal_id (FK), model, confidence (1-10), thesis, risk_factors, raw_response, response_time_ms
- **trades**: signal_id (FK), llm_analysis_id (FK), ticker, side, entry/stop/target, exit, status, pnl

## Signal Engine (6 signals — VWAP tuned, gap reclaim seeded)

| Signal | Scoring | Tuning Notes |
|---|---|---|
| **vwap_cross** | 3-gate: ≥0.15% cross, prev bar ≥0.10% on other side, ≥2x volume. Score: min(10, int(4 + vol_mult + cross_pct)), floor 7. **Both bullish and bearish.** | Tuned July 9 — was 2,612 signals (65%). 3 gates added. |
| **rsi_extreme** | Oversold: 8 + (25-rsi)/2. Overbought: 8 + (rsi-75)/2. rsi_period=14 | 901 signals (22%) |
| **opening_range_break** | 6 + breakout_pct. opening_range_minutes=15. Both directions. | 300 signals |
| **volume_spike** | 5 + volume_mult. volume_spike_mult=3.0 | 147 signals |
| **bollinger_squeeze** | 7 (fixed) when std < 0.5 and close > upper. period=20, std=2.0 | 72 signals |
| **gap_reclaim** | 5 + gap_pct. Seeds prev_close lazily from Massive REST on first ticker encounter. | 0 signals before fix — prev_close was never populated |

All scores capped at 10. Min score to trigger LLM: 7 (configurable).

### Gap Reclaim — Lazy REST Seeding

`_seed_prev_close(ticker)`: calls Massive REST `/v2/aggs/ticker/{ticker}/prev`, extracts `results[0].c`, caches in `self.prev_close`. Tag `_seeded` set to prevent repeat calls. 5s timeout, graceful degradation. Called on first bar for each ticker from `evaluate()`.

### JSON Parsing

Handles 3 fallback cases: direct JSON, markdown code block (```json), and regex extraction. Falls back to raw text with confidence=0 on parse failure. **Upgrading to qwen3:14b eliminates this complexity** via native JSON mode.

## LLM Context Layer

### Prompt structure
```
System: You are a swing trading analyst...
Context: TICKER, SIGNAL type/score/detail, recent price action, news, SEC filings
Output: JSON {thesis, confidence (1-10), risk_factors, catalyst}
```

### JSON parsing
Handles 3 cases: direct JSON, markdown code block (```json), and regex extraction of JSON object in text. Falls back to raw text with confidence=0 on parse failure.

### Decision gate
Trade only fires when: signal_score ≥ 7 AND LLM confidence ≥ 6 (both configurable in config.yaml).

## Config — What User Needs to Fill In

In `D:\swing-scope\config.yaml`:
1. `massive.api_key` — same key Vesper uses
2. `alpaca.api_key` + `secret_key` — **NEW separate paper account** (not Vesper's)
3. `risk.vesper_account_id` — Vesper's Alpaca account ID (for contamination check)

## Running

```bash
# Required: Ollama running (desktop app or ollama serve)
# Launch:
cd D:\swing-scope
PYTHONUNBUFFERED=1 ./venv/Scripts/python.exe -u -m src.main
# Or double-click: Vesper Swing.lnk (desktop shortcut)
```

**Critical**: `PYTHONUNBUFFERED=1` and `python -u` are required on Windows — without them, log output after WebSocket connection is stuck in a buffer and the process appears dead. See `references/massive-websocket-debugging.md` for full details.

## Desktop Shortcut (Windows)

Created via PowerShell COM object:
```powershell
$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('C:\Users\<user>\Desktop\Vesper Swing.lnk')
$Shortcut.TargetPath = 'D:\swing-scope\start.bat'
$Shortcut.WorkingDirectory = 'D:\swing-scope'
$Shortcut.Save()
```

## What's NOT Built Yet

- `src/execution/` — Alpaca paper order execution (Phase 3)
- `src/dashboard/` — Vesper Swing dashboard page (Phase 3)
- `ContextGatherer.get_recent_news()` — RSS feed parsing (stub returns empty)
- `ContextGatherer.get_sec_filings()` — EDGAR RSS parsing (stub returns empty)
- Position management (max 3 open, daily loss cap, EOD flat)
- Direction + stop/target generation in LLM prompt (currently just "signal detected")
- Backtesting harness for signal engine on historical Massive data
