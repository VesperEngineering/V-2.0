# VESPER 2.0 / v20 Data Architecture & Model Pipeline
## Discovered 2026-07-22 via read-only audit

## Context
The v20 codebase at `C:\Users\bgonn\Desktop\v20` is a disconnected copy of the VESPER trading engine. It configures `strategy.name: ml_model` and expects `models/xgb_ranker.json`, but the actual production model pipeline is transformer-based, not XGBoost.

## Massive Data Corpus (read-only inventory)

### Primary Stores
| Store | Path | Coverage | Tickers | Notes |
|-------|------|----------|---------|-------|
| SP500 OHLCV (consolidated) | `vesper_data/massive/sp500/sp500_ohlcv.sqlite` | 2003-09-10 → 2026-07-20 | 502 | Primary historical panel. Raw/unadjusted. |
| Normalized (broad) | `vesper_data/massive/normalized/day_aggs_coverage_expanded_*.sqlite` | 2003 → 2026 | ~36K | Per-year cumulative snapshots. 48M+ rows in latest. |
| Adjusted (active universe) | `vesper_data/massive/adjusted/*.sqlite` | 2003 → 2026-06-30 | 33 | Split/dividend adjusted. Includes SPY, QQQ, sector ETFs. |
| Total Return | `vesper_data/massive/total_return/*.sqlite` | 2003 → 2026-06-30 | 33 | Same as adjusted plus `total_return_adjusted_close`. |
| Governance | `vesper_data/massive/governance/*.sqlite` + `.json` | — | — | Alias maps (FB→META, QQQQ→QQQ), universe membership, ticker lifecycle. |
| Reference | `vesper_data/massive/reference/*.sqlite` | — | — | Corporate actions: splits, dividends. |

### Raw SIP Feeds
- `vesper_data/massive/raw/us_stocks_sip/day_aggs_v1/YYYY/MM/YYYY-MM-DD.csv.gz`
- One file per trading day, 2003 → 2026-07
- Unadjusted; columns: ticker, volume, open, close, high, low, window_start, transactions

### SP500 Daily CSVs
- `vesper_data/massive/sp500/YYYYMMDD.csv.gz` — daily snapshot of all ~502 constituents
- Consolidated SQLite also exists at `sp500_ohlcv.sqlite`

## Training Matrices: Transformers, Not XGBoost

The training arrays under `market_data/numbers/training/` are **3D sequence tensors**, not tabular XGBoost inputs.

| File | Size | Shape | Interpretation |
|------|------|-------|----------------|
| `v4_optimized/X.npy` | 2.0 GB | `(300,607, 60, 29)` | 300k samples × 60 timesteps × 29 features |
| `v4_optimized/y.npy` | 1.2 MB | `(300,607,)` | Labels |
| `v4_optimized/sectors.npy` | 1.2 MB | `(300,607,)` | Sector codes per sample |
| `v3_optimized/X.npy` | 11 GB | larger prior version | |
| `v2_5year.npz` | 1.4 GB | earlier training set | |

**Key implication:** A `(N, T, F)` shape is transformer/RNN sequence data. It cannot be consumed by XGBoost without flattening or architectural change. Any model strategy expecting `xgb.XGBRegressor().load_model("xgb_ranker.json")` is inconsistent with the actual training pipeline.

## Production Model Artifacts

Location: `D:/vesper/models/production/`

| Artifact | Size | Type | Status |
|----------|------|------|--------|
| `novaaetus_v3.pth` | 5.8 MB | PyTorch | Production transformer |
| `novaaetus_v3_5.pth` | 12.9 MB | PyTorch | Larger production variant |
| `transformer_latest.pth` | 2.6 MB | PyTorch | Latest transformer checkpoint |
| `calibrator_v3.pkl` | 1.1 KB | sklearn | Logistic calibration wrapper |
| `logistic_ensemble.joblib` | 1.4 KB | sklearn | Ensemble wrapper |
| `logistic_scaler.joblib` | 1.4 KB | sklearn | Scaler wrapper |

**No XGBoost model exists** in `production/`, `archive/`, or `training/`.

## Governance Artifacts Confirm the Story

`D:/vesper/artifacts/evals/` contains hundreds of dated JSON receipts:

- `tree_ranker_baseline_*` — tree model researched as baseline (latest 2026-07-03) but **never promoted**
- `massive_total_return_model_*` — full transformer evaluation gates, dry runs, walk-forward protocols
- `model_training_run_receipt_train_*_transformer_seed7_*` — dozens of transformer training runs
- `shadow_monitoring_daily_signal_receipt_20260703.json` — transformer actively running in shadow mode

## v20 Codebase Disconnects

1. **`engine.py` does not support `ml_model`** — only `momentum` is wired (lines 55-58).
2. **`settings.yaml` wants `ml_model`** — but the model file `models/xgb_ranker.json` does not exist.
3. **`feed.py` uses yfinance** — the local Massive SQLite stores are not connected.
4. **`ml_model.py` expects XGBoost** — loads `xgb_ranker.json`; incompatible with transformer artifacts.

## Practical Implications

- **Do not search for `xgb_ranker.json`** — it does not exist because the pipeline is transformer-based.
- **If v20 needs an ML strategy**, the choice is:
  1. **Retrain XGBoost** from scratch using Massive data (simpler, aligns with v20's current `ml_model.py`)
  2. **Adopt the transformer** (`novaaetus_v3.pth` or `transformer_latest.pth`) — requires rewriting `ml_model.py` to consume 3D sequence tensors
- **The transformer pipeline has been shadow-validated** — governance receipts prove it, but it is heavier and more complex.
- **For a "simple, no-bloat" v2.0**, an XGBoost retrain may be the right call, but it requires building a tabular feature pipeline from the Massive SQLite stores.

## Audit Commands (reproducible)

```bash
# Training matrix shapes
python -c "import numpy as np; X=np.load('D:/vesper/vesper_data/market_data/numbers/training/v4_optimized/X.npy', mmap_mode='r'); print('X:', X.shape)"
python -c "import numpy as np; y=np.load('D:/vesper/vesper_data/market_data/numbers/training/v4_optimized/y.npy', mmap_mode='r'); print('y:', y.shape)"

# Production models
ls -la D:/vesper/models/production/

# SQLite schema peek
python -c "import sqlite3; c=sqlite3.connect('D:/vesper/vesper_data/massive/sp500/sp500_ohlcv.sqlite').cursor(); c.execute(\"SELECT name FROM sqlite_master WHERE type='table';\"); print(c.fetchall())"

# Governance artifact inventory
ls D:/vesper/artifacts/evals/ | grep -E 'transformer|tree_ranker|model_training'
```
