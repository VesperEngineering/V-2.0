# Gap/Intraday Event Recovery and Structural Ablation — 2026-07-10

Use this as a dated report-only diagnostic record. It extends the first survivor-cohort stop comparison but does **not** supersede the independent mechanical/provenance review in `survivor-cohort-stop-diagnostic-review-20260710.md`.

## Reusable experiment pattern

When a bundled risk control fails, diagnose mechanism before tuning thresholds:

1. Record only trigger events for positions actually held by the simulated strategy; do not scan every raw market event and imply portfolio relevance.
2. Preserve ticker-session time: measure counterfactual recovery at the next 1, 5, and 10 sessions for that ticker, not calendar days.
3. Record trigger type, exit date, actual modeled exit price, and forward close returns. Keep missing terminal horizons explicit rather than zero-filling.
4. Split bundled controls structurally while freezing thresholds, costs, cooldown, selection logic, and the economic gate. Here, separate opening-gap-only from intraday-only; do not grid-search nearby percentages.
5. Compare Sharpe, max drawdown, worst day, turnover, risk-exit count, and stopped-name recovery. A better worst day is not a pass if prolonged drawdown worsens.
6. Keep `deployment_approved = false`; a survivor/current-sector cohort can reject a policy but cannot promote one.

## Provisional event results

From 222 selected-position exits in the bundled gap/intraday variant:

- 1-session median recovery: +0.17%; positive rate 50.9%.
- 5-session median recovery: +0.79%; positive rate 53.2%.
- 10-session median recovery: +2.24%; positive rate 57.2%.
- Opening-gap events (71): 5-session mean -0.60%, median +0.80%; 10-session median +2.26%.
- Intraday events (151): 5-session mean +1.73%, median +0.77%; 10-session median +2.22%.

These numbers measure opportunity cost from the modeled exit price. For intraday threshold fills they can include the same-day threshold-to-close rebound indirectly, so interpretation depends on valid entry/trigger ordering.

## Frozen structural ablation at 15 bps

| Variant | Sharpe | Max DD | Worst day | Risk exits | Gate |
|---|---:|---:|---:|---:|---|
| Baseline | 0.69 | -55.9% | -12.7% | 0 | baseline |
| Opening-gap only | 0.70 | -57.1% | -12.2% | 78 | rejected |
| Intraday only | 0.75 | -56.5% | -9.9% | 208 | rejected |
| Bundled gap + intraday | 0.64 | -56.7% | -10.9% | 222 | rejected |

The bundled policy is not the sum of independent event counts because each control changes exposure, cooldown, and future selection. Report this path dependence explicitly.

## Critical validity boundary

An independent review later found two defects that prevent treating these economics as decision-grade:

- A newly entered position could be bought below a pre-existing intraday threshold and then sold at the higher threshold in the same session, manufacturing an impossible favorable fill.
- GOOG/GOOGL identity and the 2014 share-class distribution were not normalized, contaminating adjusted returns and cross-sectional signals.

Therefore, do **not** encode “intraday-only is superior” as a durable conclusion. The durable conclusion is procedural: correct entry/breaker ordering and effective-dated identity first, then rerun the same frozen ablation. Do not tune thresholds between the flawed and corrected runs.

## Next bounded sequence

1. Add a synthetic regression proving no same-session risk exit can fill above a new entry price due to a threshold crossed before entry.
2. Define the canonical rule explicitly: skip the new entry, fill at entry/open, or start monitoring only after entry; choose before seeing corrected economics.
3. Normalize or exclude unresolved GOOG/GOOGL transition history and scan adjusted-return tails for other corporate-action discontinuities.
4. Emit source hashes, event ledger, equity curves, daily eligible-universe size, max-drawdown peak/trough dates, and separate administrative/risk exit counts.
5. Rerun the frozen variants and gate. If they still fail, retire the canonical specification rather than tuning nearby thresholds.
