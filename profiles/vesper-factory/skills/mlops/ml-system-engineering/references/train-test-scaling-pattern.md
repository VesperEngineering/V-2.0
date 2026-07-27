# Train-Test Cross-Sectional Z-Score Pattern

## Context
Used in VESPER 2.0 quant pipeline when training an XGBoost ranker on SP500 OHLCV data.

## Problem
Model trained on z-scored features (mean=0, std=1 per date cross-section) but inference fed raw features. Result: silent garbage predictions, zero trades in backtest.

## Training Code

```python
import pandas as pd
import numpy as np

FEATURE_COLS = [...]  # 17 feature columns

def _zscore(s: pd.Series) -> pd.Series:
    m = s.mean()
    std = s.std()
    return pd.Series(0.0, index=s.index) if std == 0 or pd.isna(std) else (s - m) / std

# Build panel: one row per (ticker, date)
rows = []
for ticker, df in bars.items():
    feats = compute_features(df)
    labels = df["close"].pct_change(5).shift(-5)
    aligned = feats.join(labels.rename("label"), how="inner").dropna()
    aligned["ticker"] = ticker
    aligned = aligned.reset_index()
    rows.append(aligned)

panel = pd.concat(rows, ignore_index=True)
panel["date"] = pd.to_datetime(panel["date"])

# Cross-sectional z-score within each date
for col in FEATURE_COLS:
    panel[col] = panel.groupby("date", group_keys=False)[col].apply(_zscore)

# Also z-score the label (ranking target)
panel["label"] = panel.groupby("date", group_keys=False)["label"].apply(_zscore)

X = panel[FEATURE_COLS].values
y = panel["label"].values
```

## Inference Code

```python
# Must build the same panel, then z-score, THEN predict
feat_rows = []
for sym, df in data.items():
    feats = compute_features(df)
    if feats.empty or feats.iloc[-1].isna().any():
        continue
    row = feats.iloc[[-1]].copy()
    row["symbol"] = sym
    feat_rows.append(row)

if not feat_rows:
    return []  # no signals

panel = pd.concat(feat_rows, ignore_index=True)
zscored = zscore_features(panel[FEATURE_COLS])  # same function as training

scores = {}
for i, sym in enumerate(panel["symbol"]):
    x = zscored.iloc[[i]].values
    pred = float(model.predict(x)[0])
    scores[sym] = pred
```

## Key Principle
The z-score statistics (mean, std) must be computed over the **same cross-section** at inference as at training. For a ranking model, that means **per-date across all stocks in the universe**, not per-stock across time.

## Verification
After wiring inference, run a backtest. If the model produces zero trades or flat P&L, check:
1. Are features being z-scored before `model.predict()`?
2. Is the z-score function identical to training?
3. Are NaN/inf values handled the same way?
