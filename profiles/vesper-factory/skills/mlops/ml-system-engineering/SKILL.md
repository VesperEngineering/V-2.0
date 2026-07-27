---
name: ml-system-engineering
description: Engineering patterns and pitfalls for deploying ML models in production systems, with emphasis on quant/trading pipelines.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [mlops, quant, model-deployment, inference, feature-engineering]
    related_skills: [surgical-engineering, test-driven-development]
---

# ML System Engineering

## Overview

Build and operate ML pipelines that don't silently fail. Covers training execution, feature scaling consistency, and observability for quant/trading systems.

This skill does **not** replace:
- `surgical-engineering` for general code-edit scope control.
- `test-driven-development` for strict RED-GREEN-REFACTOR workflows.

## 1. Terminal Execution for ML Jobs

### Rule
For a bounded one-shot training or backtest job expected to run >10 seconds, **do not poll** with repeated `terminal()` calls.

### Correct pattern
```python
terminal(
    command="python scripts/train_model.py",
    background=true,
    notify_on_complete=true,
)
```
This counts as a single tool call. The system delivers the full output on completion.

### Wrong pattern
```python
# DON'T DO THIS — burns tool-call budget
for _ in range(30):
    terminal(command="python scripts/train_model.py")
    sleep(10)
```

### When polling IS acceptable
- The process is genuinely long-lived (server, daemon, WebSocket stream).
- You need a mid-process readiness signal (e.g., "Application startup complete").
- Use `watch_patterns` for rare one-shot signals, NOT end-of-run markers.

## 2. Train-Test Feature Scaling Consistency

### Rule
If training normalizes or z-scores features, inference **must** apply the **identical** scaling over the **same cross-section**. Otherwise predictions are silently garbage.

### Common mistake
Training pipeline z-scores cross-sectionally per date:
```python
panel[col] = panel.groupby("date", group_keys=False)[col].apply(_zscore)
model.fit(panel[FEATURE_COLS], panel["label"])
```

Inference pipeline feeds raw unscaled features:
```python
feats = compute_features(df)
pred = model.predict(feats.iloc[[-1]][FEATURE_COLS])  # WRONG
```

### Correct inference pattern
Build the same cross-sectional panel at inference time, then z-score, then predict:
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

### Key check
After deploying a model, verify the first few predictions are numerically similar to training-time predictions on the same input. If they diverge, scaling mismatch is the prime suspect.

## 3. Python Logging Format Compatibility

### Rule
Python's `%`-style logging format strings do **not** support the `,` thousands separator or `+` sign flags that work in f-strings.

### Error
```python
logger.info(" equity=$%,.0f", eq)   # ValueError: unsupported format character ','
```

### Fix
Use f-strings for complex formatting, or stick to basic `%` specifiers:
```python
# f-string (safe)
logger.info(" equity=$%s", f"{eq:,.0f}")

# basic % (safe)
logger.info(" equity=$%.0f", eq)
```

## References

- `references/train-test-scaling-pattern.md` — Condensed code recipe for panel-based cross-sectional z-scoring.
