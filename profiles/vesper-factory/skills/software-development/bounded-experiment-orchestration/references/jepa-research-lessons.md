# Raw-OHLCV JEPA Research Lessons

## Empirical sequence

- A compact VICReg/JEPA-style encoder can avoid collapse and learn predictable temporal latent states.
- That technical success does not imply return direction, cross-sectional alpha, or calibrated risk forecasting.
- Cross-sectional/ranking additions can reduce baseline IC; treat that as rejection, not a tuning invitation.
- Fixed latent coordinates are not semantic identities: across seed retraining, sign and rotation may change. Evaluate subspaces/probes, not coordinate labels.
- A full latent subspace can retain stable *ordering* of contemporaneous volatility while raw numeric level calibration remains unusable; correlation and R² must be displayed separately.
- More width, horizon, or epochs may increase effective rank without material downstream improvement. A frozen ablation should report all rows.

## HUD operational lessons

- `epoch N/N` does not mean the process is complete: embedding extraction, aggregation, probe fitting, statistics, and artifact writes can be substantial.
- Emit explicit post-epoch phase lines and use `python -u` / flushed output.
- Manual terminal clear loops visibly flash. Use a managed live renderer or alternate screen, but keep output compact enough not to scroll.
- Put the one-line neural diagram near the top: `[105 input] -> [128] -> [64] -> [16 latent] -> [64] -> [16 predicted]`.

## Research queue lesson

Use continuous GPU work for fixed replicates and fixed ablations. Do not use compute availability as justification for autonomous hypothesis generation or repeated holdout tuning.
