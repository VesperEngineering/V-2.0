# V20 Model Promotion Gates — 2026-07-22

## Purpose

A trained `models/xgb_ranker.json` is a research artifact, not a deployable strategy. Establish reproducibility, engine compatibility, and comparable baselines before paper promotion.

## Required artifact sidecar

After saving a model, write `models/xgb_ranker.metadata.json` containing:

- SHA-256 of the model bytes
- label horizon and chronological split boundary
- train/OOS IC and sample counts
- exact XGBoost parameters

Verify the SHA-256 against the artifact before interpreting a result. This prevents queued or stale training runs from silently replacing the evaluated model.

## Runtime-contract smoke gate

`TradingEngine._tick()` filters bars using `self.strategy.lookback`. Every strategy, including `MLModelStrategy`, must expose this attribute. Add a focused test that loads a tiny temporary XGBoost artifact and asserts the ML strategy has the feature minimum (currently 50 sessions). Compile the trainer, strategy, and backtest runner after edits.

## Baseline gate before promotion

Run identical no-submit windows for:

1. ML model (daily cadence first for daily OHLCV)
2. Existing momentum strategy
3. Equal-weight buy-and-hold benchmark over the **actual configured universe**

State the benchmark universe truthfully: `config/universe.yaml` can be a bounded subset, so do not call it the full S&P 500 unless it contains that universe.

Do not promote when ML underperforms both controls before costs. A short recent window is diagnostic evidence only, not a deploy/paper gate; it does not replace a cost-aware, purged walk-forward evaluation.

## Current observed result

On the then-current 81-session, 100-symbol configured-universe window:

| Strategy | Return |
|---|---:|
| Equal-weight configured universe | +6.11% |
| Momentum | +5.03% |
| ML model, daily rebalance | -5.90% |

The same ML model was worse at 5- and 10-session cadence (-6.46% and -6.88%). This rejects cadence tuning as the next action. Diagnose ranking quality/feature-target design against controls instead.

## Logging pitfall

Python logging uses old `%` interpolation, not f-string format specifications. Strings such as `"$%,.0f"` cause `ValueError` when a logging handler formats the record. Use an f-string for comma-formatted currency in risk and paper-broker logs, and add a test that exercises the rejected-order or breaker path under pytest log capture.
