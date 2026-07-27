# V20 MassiveFeed Wiring and Guardrails — Session Reference

**Date:** 2026-07-22  
**Context:** VESPER 2.0 (`C:\Users\bgonn\Desktop\v20`) data provider migration  
**Key finding:** The `ml_model` default strategy is configured but not wired into the engine.

---

## What Was Done

### 1. MassiveFeed Added to `vesper/data/feed.py`

- New `MassiveFeed` class reads from local SQLite: `vesper/data/massive/sp500/sp500_ohlcv.sqlite`
- `get_bars()` returns OHLCV DataFrames keyed by symbol
- `get_latest_price()` returns most recent `close` per symbol
- `create_feed()` factory wired with `provider == "massive"`

### 2. Config Updated in `config/settings.yaml`

```yaml
data:
  provider: massive
  massive_data_dir: "vesper/data/massive"
```

### 3. Verification Pattern

Ad-hoc verification script pattern used (created in temp, executed, then cleaned up):

```python
from vesper.data.feed import MassiveFeed, create_feed
from datetime import datetime, timedelta

config = {"data": {"massive_data_dir": "vesper/data/massive"}}
feed = MassiveFeed(config)

# get_bars test
end = datetime(2026, 7, 20)
start = end - timedelta(days=60)
bars = feed.get_bars(["AAPL", "MSFT", "NVDA", "TSLA", "META"], start, end)
assert set(bars.keys()) == {"AAPL", "MSFT", "NVDA", "TSLA", "META"}

# get_latest_price test
prices = feed.get_latest_price(["AAPL", "GOOGL", "AMZN"])
assert len(prices) == 3

# factory test
factory_feed = create_feed({"data": {"provider": "massive", "massive_data_dir": "vesper/data/massive"}})
assert isinstance(factory_feed, MassiveFeed)
```

**Important:** SPY is NOT in the SP500 SQLite. The DB contains individual equities only. Use "A" (Agilent) or another known ticker for smoke tests.

---

## What Remains Open

### Engine Strategy Factory

`vesper/engine.py` lines 55–58 hardcode only `momentum`:

```python
if name == "momentum":
    self.strategy = MomentumStrategy(strat_cfg.get("params", {}))
else:
    raise ValueError(f"Unknown strategy: {name}")
```

Wiring `ml_model` requires:
1. Resolving the model artifact question (see below)
2. Adding an `elif name == "ml_model":` branch

### Model Artifact Mismatch

- `config/settings.yaml` points to `models/xgb_ranker.json` — **does not exist**
- D:/vesper production models are PyTorch transformers (`novaaetus_v3.pth`, `transformer_latest.pth`)
- Training tensors are 3D sequence data `(300k, 60, 29)` — built for transformers, not XGBoost
- No XGBoost model exists anywhere in production or archive

**Decision fork:**
1. Retrain XGBoost from scratch (aligns with v20 simplicity goal)
2. Adopt the transformer pipeline (validated but complex)

This is a strategic decision that requires user input. Do not silently choose.

---

## Data Boundaries Enforced

- `vesper/data/massive/` is **read-only** — do not write, delete, or modify
- `sp500_ohlcv.sqlite` contains **raw unadjusted prices** — split adjustment must be applied before feature computation or backtesting
- 33-ticker adjusted/total_return datasets are for validation only, not broad backtesting
- Canonical data store is `D:\vesper\vesper_data` (190+ GB); v20 `vesper/data/massive/` is a subset

---

## AGENTS.md Created

Project constitution written to `C:\Users\bgonn\Desktop\v20\AGENTS.md` containing:
- Mandatory pre-flight checklist (skills + codegraph + guardrails)
- Product direction (`ml_model` default, simplicity first)
- Data boundaries (read-only massive data)
- Model & strategy constraints (missing artifact, no fabrication)
- Execution authority (denied vs allowed)
- Verification requirements (no fabrication rule)
- Anti-patterns table from EXAMPLES.md

Future agents must read this file before editing v20 code.

---

## Commands for Reproducing the Audit

```bash
# Check SP500 DB coverage
sqlite3 vesper/data/massive/sp500/sp500_ohlcv.sqlite \
  "SELECT MIN(date), MAX(date), COUNT(DISTINCT ticker) FROM sp500_ohlcv;"

# Check if model artifact exists
ls models/xgb_ranker.json 2>/dev/null || echo "MISSING"

# Check D:/vesper transformer artifacts
ls /d/vesper/models/production/*.pth

# Check training tensor shapes
python -c "import numpy as np; X=np.load('D:/vesper/vesper_data/market_data/numbers/training/v4_optimized/X.npy', mmap_mode='r'); print('X shape:', X.shape)"
```
