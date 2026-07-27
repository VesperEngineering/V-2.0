---
name: self-supervised-finance
description: Self-supervised learning approaches (JEPA, VICReg, contrastive learning) for financial time series — research, prototyping, and evaluation.
---

# Self-Supervised Learning for Finance

Techniques for learning useful market representations from unlabeled financial
time-series data. The core idea: instead of predicting raw prices or returns
(supervised), learn a latent embedding space that captures market structure
through temporal or cross-sectional self-supervision.

## When to Load This Skill

- User asks about representation learning, JEPA, VICReg, SimCLR, BYOL, or
  self-supervised approaches for financial data
- Research spike into non-supervised ML for quant finance
- Evaluating whether a learned latent representation adds value beyond
  hand-crafted factors
- Any "what if we train a model to learn market structure without labels" idea

## Core Approaches

### JEPA (Joint Embedding Predictive Architecture)

LeCun's paradigm: predict future **representations**, not future observations.

```
Input sequence → Encoder → Current embedding z_t
                              ↓
                        Latent Predictor → ẑ_{t+k}
                              ↓
                 VICReg Loss (variance + invariance + covariance)
```

**Key advantage:** the predictor operates on a 16-64 dim latent vector instead
of the full input, saving O(n²) attention cost. The encoder learns to compress
market state into a usable representation.

**Components:**
- **Encoder** — maps raw input (OHLCV window, features) into latent embedding
- **Latent Predictor** — forecasts future embeddings; operates in latent space
- **VICReg Loss** — three terms prevent collapse:
  - *Variance* — spread latent dims across batch (std ≥ 1.0, coefficient α≈25)
  - *Invariance* — MSE between predicted and target embeddings (β≈1)
  - *Covariance* — off-diagonal ≈ 0, orthogonal dimensions (γ≈1)

### VICReg (Variance-Invariance-Covariance Regularization)

Self-supervised loss that prevents representation collapse without requiring
negative pairs (contrastive) or a target network (BYOL). Works well with small
batch sizes.

### Why Self-Supervised for Finance

- **Labels are scarce** — future-return thresholds are arbitrary and noisy.
  Self-supervised learning uses the temporal structure of the data itself.
- **Non-stationarity** — the market regime changes. A self-supervised model
  can continuously adapt its representation.
- **Complementary to factors** — the latent embedding can be used as a new
  input to the existing factor pipeline, not as a replacement.

## Trade-Offs vs. Supervised Learning

| Dimension | Supervised (current transformer) | Self-Supervised (JEPA) |
|-----------|----------------------------------|------------------------|
| Labels | Future-return threshold | None — temporal structure |
| Loss | Cross-entropy / MSE on returns | VICReg on latent space |
| Evaluation | Classification accuracy, FM | Linear probe, embedding quality |
| Infrastructure | Fits existing governance | Needs new evaluation gates |
| Compute | Moderate | Higher (encoder + predictor + regularizer) |
| Interpretability | Opaque (transformer) | Opaque (latent space) |

## Pitfalls

1. **Encoder collapse is the most likely failure mode.** VICReg hyperparameters
   (α, β, γ) are sensitive. If the variance term is too weak, all latents
   converge to a constant. Check latent std dev after 10 epochs. **In practice,
   a 12K-parameter MLP encoder with standard VICReg (α=25, β=25, γ=1) does NOT
   collapse on OHLCV data — this was validated in a 2026-07-16 spike.**

2. **Cross-sectional vs. sequential encoding** is a fundamental design choice:
   - Per-ticker sequential: each ticker is its own sequence. Sparse per-ticker,
     rich temporal structure. Encoder processes one ticker at a time.
   - Cross-sectional snapshot: all tickers as one wide observation. Richer per-day
     representation but loses the memory advantage if you encode full cross-section.

3. **CPU-only training is a bottleneck for large datasets.** A 64-dim, 2-layer MLP JEPA with
   VICReg on 100 tickers × 5000 days converges in ~3 minutes on CPU. On the full
   500-ticker universe, expect ~15 minutes per 10 epochs. Train on a 50-100 ticker
   subset first to validate the architecture, then scale up. Getting a GPU is only
   necessary for deeper architectures (6+ layers, transformers, or full cross-sectional encoding).

4. **Regime shifts break the predictor.** A model trained on 2004-2020 will
   predict 2021-2026 embeddings poorly if the market regime changed. This is
   correct behavior but makes evaluation ambiguous.

5. **Downstream evaluation is not Fama-MacBeth.** The latent embedding is a
   vector, not a scalar factor. Use linear probes, regression of embedding
   dimensions on forward returns, or cluster purity analysis instead.

## Evaluation Framework

Since FM regression (|t| > 2.0) doesn't apply to multi-dimensional embeddings:

- **Linear probe:** train a linear classifier on frozen embeddings → predict
  next-week return direction. AUC > 0.55 suggests signal.
- **Factor correlation:** correlate each latent dimension with known risk
  factors (momentum, low-vol, value, size). Interpretable if dimensions align.
- **Regime separation:** do PCA/UMAP clusters separate high-vol from low-vol
  regimes, bull from bear?
- **Prediction horizon sweep:** 1d, 5d, 21d prediction quality degrades
  gracefully (not dropping off a cliff after 3d).

## Related Papers

- LeCun (2022) "A Path Towards Autonomous Machine Intelligence"
- Bardes et al. (2022) "VICReg: Variance-Invariance-Covariance Regularization"
- Assran et al. (2023) "I-JEPA: Self-Supervised Learning from Images with a Joint-Embedding Predictive Architecture"
- Baevski et al. (2023) "data2vec: A General Framework for Self-supervised Learning in Speech, Vision and Language"
- Balestriero & LeCun (2024) "How JEPA Works" (video lecture series)

## References

- `references/jepa-finance-research-spike.md` — decomposition of JEPA research
  into 3 feasibility spikes, with architecture sketch, loss function, and
  evaluation criteria. Start here when beginning a new research session.