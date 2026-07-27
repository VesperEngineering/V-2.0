# V20 Model Training Pattern

Chronological train/test split for time-series financial ML using local Massive SQLite data.

## Context

The v20 codebase (`C:\Users\bgonn\Desktop\v20`) configures `ml_model` as its default strategy. The training pipeline reads from `vesper/data/massive/sp500/sp500_ohlcv.sqlite` (raw SP500 OHLCV) and trains an `xgboost.XGBRegressor` to predict 5-day forward returns.

## Anti-pattern: random or in-sample validation

Do NOT shuffle samples or report in-sample IC. Financial data is autocorrelated; random splitting leaks future information into training. A 0.95+ in-sample IC is a red flag for overfitting, not a good result.

## Correct pattern: chronological split

```python
# build_training_set returns dates alongside X, y
X, y, dates = build_training_set(bars)

cutoff = np.datetime64("2021-01-01")
train_mask = dates < cutoff
test_mask  = dates >= cutoff

X_train, y_train = X[train_mask], y[train_mask]
X_test,  y_test  = X[test_mask],  y[test_mask]

model = xgb.XGBRegressor(...)
model.fit(X_train, y_train)

train_ic = np.corrcoef(model.predict(X_train), y_train)[0, 1]
test_ic  = np.corrcoef(model.predict(X_test),  y_test)[0, 1]
```

Report **test IC** (out-of-sample) as the primary metric. Train IC is only a sanity check.

## Data flow

1. `load_bars()` → read `sp500_ohlcv.sqlite` into `dict[ticker, DataFrame]`
2. `compute_features()` → `vesper/data/features.py` (tabular OHLCV features)
3. `df["close"].pct_change(5).shift(-5)` → forward 5-day return label
4. Align features + labels, drop NaN, split chronologically
5. Train, evaluate, save to `models/xgb_ranker.json`

## Key files

- `scripts/train_model.py` — training entry point
- `vesper/strategy/ml_model.py` — strategy that loads the trained model
- `vesper/data/features.py` — feature computation
- `config/settings.yaml` — strategy configuration

## Missing model artifact pitfall

If `models/xgb_ranker.json` does not exist, `MLModelStrategy` raises `FileNotFoundError` at engine startup. Always train before switching `strategy.name` to `ml_model`.
