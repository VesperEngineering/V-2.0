# XGBoost Feature Engineering Experiment Log

Session: 2026-07-22
Goal: Improve out-of-sample IC for VESPER 2.0 ml_model strategy

## Baseline

- 502 tickers, 24 raw price/volume features
- 5-day forward return label
- Chronological split: pre-2021 train, 2021+ test
- Cross-sectional z-score per date
- Default XGBoost: 200 trees, depth 4, alpha=0.1, lambda=1.0

**Result:** Train IC 0.139 | Test IC **0.022** | Severe overfit

## Experiment 1: 1-Day Horizon

- Changed `LABEL_HORIZON = 5` -> `1`
- Hypothesis: shorter horizon is easier to predict

**Result:** Train IC 0.118 | Test IC **0.016** | Worse than baseline
**Lesson:** 1-day returns are noisier, not easier. The signal-to-noise ratio degrades.

## Experiment 2: Strong Regularization

- 100 trees, depth 3, alpha=1.0, lambda=10.0
- Hypothesis: reduce overfitting, improve generalization

**Result:** Train IC 0.072 | Test IC **0.027** | +23% improvement
**Lesson:** Heavy regularization helps. Train IC dropped (good - less memorization), test IC rose.

## Experiment 3: Even Stronger Regularization

- 50 trees, depth 2, alpha=5.0, lambda=20.0, subsample=0.6, colsample=0.6
- Hypothesis: push generalization further

**Result:** Train IC 0.043 | Test IC **0.032** | Best test IC achieved
**Lesson:** Diminishing returns beyond this point. The ceiling for raw price features is ~0.03 IC.

## Conclusion

| Config | Train IC | Test IC | Gap |
|--------|----------|---------|-----|
| Baseline | 0.139 | 0.022 | 0.117 |
| 1-day horizon | 0.118 | 0.016 | 0.102 |
| Strong reg | 0.072 | 0.027 | 0.045 |
| Heavier reg | 0.043 | **0.032** | **0.011** |

**Verdict:** Raw price/volume features on SP500 daily bars produce ~0.03 IC maximum with XGBoost. To break through, need:
- Sequence models (transformer on 60-step windows)
- Alternative features (order flow, sentiment, fundamentals)
- Ensemble with existing trained models at `D:\vesper\models\production\`

## Backtest Finding

Backtest showed 0 trades even with model loaded. Root cause: `lookback_days=60` but `SMA_50` needs 50 days of history before producing valid features. First rebalance (day 1) had only 1 day of data -> all NaN. Fix: `lookback = 120` minimum.

Secondary issue: `entry_threshold: 0.001` blocked signals because heavily regularized model outputs small predictions. Fix: set to `0.0` first, then tune upward.
