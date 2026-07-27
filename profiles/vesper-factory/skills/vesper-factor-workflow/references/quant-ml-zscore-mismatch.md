# Quant ML Train/Test Mismatch — Cross-Sectional Z-Score

## Problem

When a model is trained on cross-sectionally z-scored features (standardized within each date across all stocks), but inference feeds raw unscaled features for a single stock, predictions are meaningless. The model learned patterns in z-score space, not raw price space.

## Real Example

- `train_model.py`: z-scores features panel-wide before training
- `MLModelStrategy`: computed features per-stock, fed raw values to `model.predict()`
- Result: out-of-sample IC = 0.022 (noise), zero trades in backtest

## Fix

At inference, compute features for **all** candidate stocks, build a panel DataFrame, apply `zscore_features()` cross-sectionally, then predict:

```python
feat_rows = []
for sym, df in data.items():
    feats = compute_features(df)
    row = feats.iloc[[-1]].copy()
    row["symbol"] = sym
    feat_rows.append(row)

panel = pd.concat(feat_rows, ignore_index=True)
zscored = zscore_features(panel[FEATURE_COLS])

for i, sym in enumerate(panel["symbol"]):
    pred = model.predict(zscored.iloc[[i]].values)[0]
```

## Diagnostic Checklist

| Symptom | Likely Cause |
|---------|-------------|
| Train IC 0.95+, Test IC < 0.05 | Overfitting OR train/test preprocessing mismatch |
| Zero trades in backtest | Predictions below threshold because scaling is wrong |
| Model loads fine, no errors | Silent mismatch — model runs but on wrong feature distribution |

## Rule

**The preprocessing pipeline at inference must exactly match the training pipeline.** If training uses z-scoring, ranking, log-transform, or winsorization, inference must apply the same operations in the same order on the same cross-section.
