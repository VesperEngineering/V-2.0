---
vesper_id: v20-quant-research
vesper_kind: skill
vesper_status: approved
vesper_scope: shared
title: V20 quantitative research guardrails
tags:
  - quant
  - data
  - factors
  - models
---
# V20 quantitative research guardrails

## When to use

Use for market data, factors, features, labels, backtests, model evaluation, or research artifacts.

## Procedure

1. Treat `vesper/data/massive/` and `vesper/data/model_research/` as protected read-only inputs.
2. Verify data identity, coverage, point-in-time availability, universe, adjustment state, and model metadata before analysis.
3. Require verified split-adjusted prices for price-derived features, labels, training, and backtests; fail closed if unavailable.
4. Use chronological train/selection/untouched-holdout boundaries with leakage controls appropriate to the horizon.
5. Fit normalization on allowed training data only and reproduce the same transformation at inference.
6. Compare against a simple baseline, freeze the contract before evaluation, and record exact artifacts, hashes, metrics, and warnings.
7. Keep research evidence separate from model promotion, capital allocation, risk changes, or trading authority.

Missing, stale, conflicting, or provenance-unbound evidence is unavailable—not permission to infer or fabricate it.
