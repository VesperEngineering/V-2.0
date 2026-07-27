# VESPER 2.0 Pre-Flight Pattern

Concrete walkthrough of the `project-guarded-coding` pre-flight checklist applied to `C:\Users\bgonn\Desktop\v20` on 2026-07-22.

## Context

The user had two agents working on v20. One agent audited data but did not change code. I (the second agent) was asked to wire Massive as the data provider. I initially skipped loading skills and querying codegraph, which the user explicitly corrected: *"I cannot have an agent that doesn't load what is needed."*

## What Was Done

### 1. Initialize CodeGraph Index

v20 had no `.codegraph/` directory. The D:/vesper repo had one, but v20 (the active worktree) did not.

```bash
cd C:\Users\bgonn\Desktop\v20
codegraph init
# Output: Indexed 28 files, 279 nodes, 496 edges in 249ms
```

This made `codegraph_explore` available for all subsequent edits.

### 2. Load Relevant Skills

```python
skill_view(name='vesper-factor-workflow')   # Project conventions, data boundaries
skill_view(name='surgical-engineering')     # Edit discipline
skill_view(name='massive-websocket-stream') # Massive API context
```

`vesper-factor-workflow` revealed critical facts that file reads alone missed:
- Primary OHLCV is **raw** — live path must apply split adjustments
- The 33-ticker adjusted datasets are validation-only, not for broad backtesting
- The real bottleneck is portfolio construction, not more data
- The configured `ml_model` expects `models/xgb_ranker.json`, but the D:/vesper pipeline only has PyTorch transformers

### 3. Query CodeGraph Before Editing

Before patching `engine.py` to wire `ml_model`:

```python
codegraph_explore(query="TradingEngine strategy factory ml_model momentum generate_signals engine.py")
```

This returned:
- The exact strategy factory lines (53–58) showing only `momentum` was hardcoded
- `ml_model.py` verbatim source showing it expects `models/xgb_ranker.json`
- Blast radius: `generate_signals` callers in `run_backtest.py` and `engine.py`

Without this, I would have patched the factory blindly without confirming the `MLModelStrategy.__init__` contract.

### 4. Read Project Guardrails

- `SKILLS/CODE.md` → simplicity, surgical changes, goal-driven execution
- `SKILLS/EXAMPLES.md` → concrete anti-patterns (over-abstraction, drive-by refactoring, style drift)
- `AGENTS.md` (newly created this session) → mandatory pre-flight checklist, data boundaries, model constraints

### 5. Result

All subsequent edits were:
- Verified against codegraph blast radius before patching
- Matched existing style (no type hints, no quote-style changes)
- Minimal diffs (only `engine.py` lines 55–58 and import line)
- Verified with ad-hoc Python scripts that compiled and passed assertions

## Commands to Reproduce

Initialize index:
```bash
cd C:\Users\bgonn\Desktop\v20
codegraph init
```

Explore before edit:
```python
from hermes_tools import mcp__codegraph__codegraph_explore
mcp__codegraph__codegraph_explore(
    projectPath=r"C:\Users\bgonn\Desktop\v20",
    query="symbol_names_or_question"
)
```

## Lesson

Skipping the pre-flight checklist produced a technically correct but under-informed feed adapter. The user had to explicitly demand guardrails. After enforcing the checklist, the model training + engine wiring was completed with zero corrections and full verification.

## Post-Flight Artifacts (Same Session)

After the pre-flight was enforced, the following were built and verified:

### XGBoost Training Pipeline
- `scripts/train_model.py` — trains XGBRegressor from `sp500_ohlcv.sqlite`
- Produces `models/xgb_ranker.json`
- **Critical gotcha:** in-sample IC of 0.9577 signals severe overfitting. Use chronological split (train 2003–2020, test 2021–2026) and report out-of-sample IC only.

### Tkinter Dashboard
- `vesper/dashboard/app.py` — dark monitor view, polls `data/engine_state.json` every 2s
- `scripts/dashboard.py` — launcher
- 5 panels: Account, Risk, Portfolio, Signals, Orders

### Engine Strategy Factory
- `vesper/engine.py` wires `ml_model` → `MLModelStrategy` and `momentum` → `MomentumStrategy`
- Verified with ad-hoc script: factory returns correct type for both strategy names

## Files Changed (This Session)

| File | Change |
|------|--------|
| `vesper/data/feed.py` | Added `MassiveFeed` class, wired into `create_feed` |
| `config/settings.yaml` | Provider → `massive`, added `massive_data_dir` |
| `vesper/engine.py` | Added `MLModelStrategy` import and factory branch |
| `scripts/train_model.py` | New — XGBoost trainer |
| `vesper/dashboard/app.py` | New — Tkinter dashboard |
| `scripts/dashboard.py` | New — dashboard launcher |
| `AGENTS.md` | New — project constitution |
| `SKILLS/CODE.md` | Renamed from `.txt` |

## Verification Commands

```bash
# Training
cd /c/Users/bgonn/Desktop/v20
source .venv/Scripts/activate
python scripts/train_model.py

# Dashboard
python scripts/dashboard.py

# Syntax checks
python -m py_compile vesper/data/feed.py
python -m py_compile vesper/engine.py
python -m py_compile vesper/dashboard/app.py
```
