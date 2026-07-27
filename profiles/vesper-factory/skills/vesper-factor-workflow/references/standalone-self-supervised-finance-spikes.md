# Standalone Self-Supervised Finance Spikes

Use this only for research that is deliberately isolated from the Vesper production path. It records a compact JEPA/VICReg experiment pattern and its rejection discipline.

## Isolation contract

- Create a separate folder and virtual environment; copy only the minimum read-only inputs.
- Do not import Vesper application code or write to its data, model registry, factor registry, scheduler, weights, broker, or dashboard.
- Record exact data copy/provenance, model/device, hyperparameters, split dates, and artifacts.
- A research result does not grant production authority, even if positive.

## Staged protocol

1. **Representation health:** verify non-collapse (per-dimension std, effective rank, sampled cosine similarity). Avoid all-pairs similarity matrices: they are O(N²) memory.
2. **Latent dynamics:** compare a temporal predictor against a persistence baseline. This proves learned predictability only, not economic usefulness.
3. **Downstream probe:** freeze the encoder and use chronological OOS evaluation. A representation trained on all dates cannot be used in an OOS claim.
4. **Cross-sectional question:** if testing ranking, use causal/split-adjusted features, fit all transforms and models before the test date, apply an embargo at least as long as the feature/lookahead overlap, and evaluate daily cross-sections with Newey-West lag appropriate to the forward-return overlap.
5. **Stop rule:** failed holdout evidence kills that exact hypothesis. Do not architecture-tune, retain a zero-weight placeholder, or reuse that holdout to recover the result. A new target/question requires a separately declared protocol.

## Data and evaluation pitfalls

- Primary OHLCV can be raw. For price/return features, copy and apply the split-adjustment map locally; never infer that a copied database is adjusted.
- Exclude instruments lacking sufficient pre-test history to fit their scaler and construct an embargoed training window. Empty pre-test scalers produce NaNs and invalidate a fold.
- Check target distributions before choosing level-RMSE. Positive dispersion/risk targets can have extreme structural tails; if a log target is required, treat it as a new pre-specified experiment, not a rescue of the prior result.
- Correlation is not enough for a risk forecast: retain calibration/level error as a primary metric. A model with higher correlation but substantially worse RMSE is not usable.
- GPU use should be measured, not assumed. Very small models with small batches can be slower on GPU due to host-device transfer; increase batch size within VRAM before drawing conclusions about accelerator value.

## Result interpretation

A compact JEPA may produce non-collapsed and temporally predictable embeddings while still adding no directional, cross-sectional, or risk forecasting value. Keep these claims separate. For Vesper-style research, FM/Newey-West evidence overrides architectural novelty, probe accuracy, or latent-space aesthetics.
