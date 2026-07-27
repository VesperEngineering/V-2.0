# V20 Model Training Pipeline Pitfalls (2026-07-22)

Session-specific reference documenting three critical bugs discovered while wiring V20's XGBoost ranker and backtest pipeline.

## 1. Train-Test Z-Score Mismatch (Critical)

**Symptom:** Model trains successfully (train IC ~0.12, test IC ~0.02) but backtest produces zero trades and 0% return.

**Root cause:** `train_model.py` z-scored features cross-sectionally within each date during training. `MLModelStrategy.generate_signals()` fed raw unscaled features at inference. The model learned weights for standardized inputs but received raw inputs — predictions collapsed to near-zero, no signal exceeded the entry threshold.

**Fix:** `MLModelStrategy` must compute features for ALL stocks, build a panel DataFrame, then call `zscore_features(panel[FEATURE_COLS])` before predicting:

```python
# In MLModelStrategy.generate_signals()
feat_rows = []
for sym, df in data.items():
    feats = compute_features(df)
    row = feats.iloc[[-1]].copy()
    row["symbol"] = sym
    feat_rows.append(row)

panel = pd.concat(feat_rows, ignore_index=True)
zscored = zscore_features(panel[FEATURE_COLS])

for i, sym in enumerate(panel["symbol"]):
    x = zscored.iloc[[i]].values
    pred = float(self.model.predict(x)[0])
```

**Verification:** After fix, backtest generates actual BUY/CLOSE signals instead of zero trades.

## 2. Windows CP1252 YAML Decode Error

**Symptom:** `run_backtest.py` crashes on launch with `UnicodeDecodeError: 'charmap' codec can't decode byte 0x90 in position 995`.

**Root cause:** `config/settings.yaml` contains Unicode characters (em dashes `—`, arrows). Python's default `open()` on Windows uses `cp1252` encoding, which cannot decode these characters.

**Fix:** Always specify `encoding="utf-8"` when opening config files:

```python
with open("config/settings.yaml", encoding="utf-8") as f:
    config = yaml.safe_load(f)
```

**Verification:** Backtest loads config without decode errors.

## 3. Python `%` Logging Format vs Thousands Separators

**Symptom:** Log messages raise `ValueError: unsupported format character ','` at index N.

**Root cause:** Python's `%` string formatting (used by `logging`) does NOT support `,` thousands separators. The format string `$%,.2f` is valid for f-strings and `.format()` but invalid for `%` formatting.

**Fix:** Use f-strings for comma-separated numeric formatting in log messages:

```python
# BROKEN — raises ValueError
logger.info(" equity=$%,.2f", equity)

# WORKING — f-string with comma separator
logger.info(" equity=$%s", f"{equity:,.2f}")
```

**Files affected:** `vesper/execution/broker.py`, `vesper/risk/limits.py`, `scripts/run_backtest.py`.

## 4. Tool-Calling Workflow for Long Jobs

**Lesson:** Do not poll long-running processes with repeated `terminal()` calls. For a one-shot job expected to take ~26–60 seconds, use:

```python
terminal(
    command="python scripts/train_model.py",
    background=true,
    notify_on_complete=true,
)
```

This counts as 1 tool call, runs asynchronously, and pings with full output on completion. If mid-run progress is needed, redirect to a log file (`--log-file logs/train.log`) and tail it, rather than re-invoking the command.

## Related References

- `references/v20-massivefeed-wiring-and-guardrails-20260722.md` — Data boundaries and provider wiring
- `references/v20-model-training-pattern.md` — Historical training pattern notes
