# Swing Scope — LLM-Augmented Intraday Trading Architecture

## Concept

A second trading strategy that runs alongside Vesper (factor-based, days-to-weeks horizon) using:
- Traditional price-action signal engine for setup detection
- Local LLM as real-time context/filter layer (zero token cost)
- Separate Alpaca account, separate codebase, separate capital

## Architecture

```
┌─────────────────────────────────────────┐
│           VESPER (unchanged)            │
│  Factor pipeline, daily scoring,        │
│  overnight positions, weekly+ horizon   │
└─────────────────────────────────────────┘
              (runs independently)

┌─────────────────────────────────────────┐
│        SWING SCOPE (new, local)         │
│                                         │
│  1. DATA INGESTION (real-time)          │
│     ├─ Massive WS minute aggregates     │
│     ├─ SEC EDGAR filings (real-time)    │
│     └─ RSS feeds / social sentiment     │
│                                         │
│  2. TRADITIONAL SIGNAL ENGINE           │
│     ├─ Gap up/down detection            │
│     ├─ VWAP reclaim / cross             │
│     ├─ Volume spike (3x average)        │
│     ├─ RSI extremes, bollinger squeeze  │
│     └─ Intraday momentum / reversal     │
│     → outputs: numerical setup scores   │
│                                         │
│  3. LLM CONTEXT LAYER (Ollama, local)   │
│     ├─ Reads incoming news → sentiment   │
│     ├─ Classifies market regime          │
│     ├─ Connects signals to context      │
│     └─ Generates trade thesis + conf.   │
│                                         │
│  4. DECISION GATE                        │
│     ├─ Signal score × LLM confidence    │
│     ├─ Risk filter (size, max loss,     │
│     │  correlation vs Vesper holdings)  │
│     └─ Alert to dashboard OR auto-exec  │
│                                         │
│  5. POSITION MANAGER                     │
│     ├─ Entry, stop, target              │
│     ├─ Time-based exit (EOD flat)       │
│     └─ Trailing stops                    │
└─────────────────────────────────────────┘
```

## Signal Engine — Price Action Setups

Traditional code (pandas, ta-lib), NOT the LLM:

| Setup | Detection Logic | Use Case |
|---|---|---|
| Gap reclaim | Open gaps >1% then reclaims VWAP | Reversal entry |
| VWAP cross | Price crosses above/below VWAP with volume | Trend continuation |
| Volume spike | Volume > 3x 20-bar average | Confirmation signal |
| RSI extreme | RSI < 30 (oversold) or > 70 (overbought) | Mean reversion |
| Bollinger squeeze | Band width < 20th percentile | Breakout pending |
| Range break | Price breaks N-bar high/low | Momentum entry |

## LLM Context Layer Prompts

When signal engine flags a setup, the LLM receives:

```
SYSTEM: You are a financial analyst evaluating an intraday trading setup.
Return JSON: {"thesis": "...", "confidence": 1-10, "risk_factors": [...], "regime": "trending|reversing|choppy"}

USER:
Setup: {setup_type} on {ticker}
Current price: {price}, VWAP: {vwap}, RSI: {rsi}
Volume: {vol} ({vol_multiple}x average)
Recent news:
- {news_headline_1}
- {news_headline_2}
Sector performance today: {sector_data}
Vesper existing positions: {vesper_positions_for_ticker}

Is there a coherent thesis supporting this move, or is it noise?
```

## Contamination Isolation Checklist

- [ ] Separate Alpaca account (different API keys)
- [ ] Separate project directory (e.g., `D:\swing-scope`)
- [ ] Separate Python venv
- [ ] Separate database (SQLite or Postgres)
- [ ] Separate capital allocation ($3-5K for Swing Scope)
- [ ] Dashboard: separate tab/page, shared frontend only
- [ ] No shared imports between Vesper and Swing Scope codebases
- [ ] Correlation check: Swing Scope cannot take position that opposes Vesper holding on same ticker

## LLM Model Selection for This Use Case

| Task | Model | VRAM | Why |
|---|---|---|---|
| News sentiment + thesis | Qwen 2.5 14B (Q4) | ~9GB | Strong reasoning, fits 16GB VRAM |
| Fast classification | Qwen 2.5 7B (Q4) | ~5GB | Quick filtering, low latency |
| Embeddings (RAG) | nomic-embed-text | ~0.5GB | SEC filing similarity search |
| Regime classification | Qwen 2.5 14B | ~9GB | Connects multiple indicators |

All run on user's existing RTX 5070 Ti. No new hardware needed for Phase 1-3.

## Economics

| Item | Cost |
|---|---|
| Massive API (already paid) | $199/mo (existing) |
| Ollama + local LLM | $0 (free, runs on existing GPU) |
| Alpaca paper trading | $0 |
| Separate codebase | $0 |
| Benzinga news add-on (optional, Phase 3+) | $99/mo |
| **Total new cost to start** | **$0** |

## Open Questions

1. Does the LLM confidence score correlate with actual trade success? (Only answerable via forward testing)
2. How many signals per day across the S&P 500 universe? (Needs Phase 1 observation)
3. What's the optimal LLM model size for this task? (14B vs 7B — tradeoff between quality and speed)
4. Is Benzinga news worth $99/mo, or are free RSS/EDGAR sources sufficient? (Test free first)

## Recommendation

Let Vesper go live first ($3K test, prove factor model with real money). Then build Swing Scope as the next project. The data infrastructure (Massive Advanced) and LLM hardware (5070 Ti) are already in place — no new spending needed to start.
