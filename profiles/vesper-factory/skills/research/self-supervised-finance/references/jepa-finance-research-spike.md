# JEPA for Finance — Research Spike Plan

Decomposition of a Joint Embedding Predictive Architecture (JEPA) applied to
financial time-series data, originally planned for the Vesper quant system.

## Origin Session

2026-07-16: Curiosity-driven exploration after watching LeCun's JEPA lecture.
The user noted the memory-efficiency angle — latent-space prediction saves
O(n²) attention cost — and wanted to prototype a minimal version as a
research experiment.

## The Three Spikes

Ordered by risk — the highest-risk question fires first:

| # | Spike | Validates (Given/When/Then) | Risk |
|---|-------|----------------------------|------|
| 001 | Encoder doesn't collapse | Given OHLCV sequences, when trained with VICReg, encoder produces a non-collapsed latent space with meaningful variance | **High** — encoder collapse kills the whole idea |
| 002 | Predictor learns temporal structure | Given a working encoder, the latent predictor beats a trivial "copy-paste" baseline (predict current embedding for all future timesteps) | High |
| 003 | Latent structure correlates with returns | Given trained embeddings, latent space shows structure correlated with forward returns, volatility, or known risk factors | Medium |

## Architecture Sketch

```
Input (21d OHLCV window, per-ticker or cross-sectional)
    │
    ▼
Encoder (2-layer MLP or tiny transformer, 16-64 dim latent)
    │
    ├──► Current embedding z_t
    │
    ▼
Latent Predictor (2-layer MLP)
    │
    ▼
    Predicted embedding ẑ_{t+k}
    │
    ▼
VICReg Loss:
  ├── Variance term — spread latent dims across batch (std dev ≥ 1.0)
  ├── Invariance term — MSE between predicted and target embeddings
  └── Covariance term — off-diagonal ≈ 0 (non-redundant dims)
```

### VICReg Loss

```
L = α * (1/d) * Σ_j max(0, 1 - std(z_j))    # variance
  + β * MSE(z_pred, z_target)                 # invariance  
  + γ * (1/d) * Σ_{i≠j} C_ij²                # covariance
```

C = covariance matrix of embeddings, d = latent dimension.
Typical values: α=25, β=1, γ=1.

## Available Data Infrastructure (Vesper repo)

- **`deploy/src/na/dl.py`** — `MarketTransformer`, `MarketLSTM`, `PositionalEncoding`, `TransformerModelConfig`
- **`deploy/src/na/transformer_training.py`** — sequence building, feature engineering, training loop, label generation
- **`deploy/src/na/features.py`** — technical features (returns, volatility, RSI, MACD, VWAP, entropy, Hurst, cross-sectional ranks)
- **`models/production/transformer_latest.pth`** — already-trained transformer
- **PyTorch 2.12.1 (CPU only)** — no CUDA, training is slow
- **~500 S&P tickers, 2003-2026 daily OHLCV** in SQLite at `vesper_data/massive/sp500/sp500_ohlcv.sqlite`
- **Model governance** — elaborate promotion gates, training receipts, approval packets. JEPA evaluation doesn't fit this framework; use notebook-style research outside governance.

## Evaluation Criteria per Spike

### Spike 001 — Encoder passes
- Each latent dimension has std dev > 0.5 across the batch (not collapsed)
- Different tickers on same date produce distinguishable embeddings
- Same ticker on different dates produces embeddings that vary with market state
- PCA/UMAP of embeddings colored by sector, year, or volatility regime

### Spike 002 — Predictor passes
- Prediction MSE < "copy-paste" baseline MSE (predict z_t for z_{t+k})
- Prediction error correlates with market volatility (higher vol = harder to predict)
- Horizon-sweep: 1d, 5d, 21d prediction quality degrades gracefully

### Spike 003 — Downstream utility
- Linear probe on embeddings predicts next-week return direction with AUC > 0.55
- Embedding dimensions correlate with known risk factors (momentum, low-vol, value)
- t-SNE/UMAP separates high-vol vs low-vol regimes

## Pitfalls Encountered

1. **Web search was unavailable during the session** (Firecrawl billing). The
   session relied on existing knowledge of JEPA literature. Add caching or
   offline reference material if this research continues.

2. **CPU-only training is the binding constraint.** A 64-dim, 2-layer MLP JEPA
   with VICReg on 500 tickers × 5000 days will take hours to converge. Batch
   size constrained by memory. Train on a 50-ticker subset first.

3. **The existing transformer training code uses binary classification labels**
   (future return above/below threshold). JEPA needs unlabeled sequences with
   temporal pairing. The data pipeline can be reused, but the label generation
   and loss function must be rewritten.

4. **Cross-sectional vs. sequential encoding** is unresolved:
   - Per-ticker sequential: ~500 sequences × 5000 days. Rich temporal structure
     per ticker. JEPA predictor learns per-ticker dynamics.
   - Cross-sectional snapshot: one sequence × 5000 days, 500-ticker-wide input.
     Richer per-day representation but loses O(n²) savings if full cross-section
     is the input token set.

## Related Work

- LeCun (2022) "A Path Towards Autonomous Machine Intelligence"
- Bardes et al. (2022) "VICReg: Variance-Invariance-Covariance Regularization"
- Assran et al. (2023) "Self-Supervised Learning from Images with a Joint-Embedding Predictive Architecture" (I-JEPA)
- Baevski et al. (2023) "data2vec: A General Framework for Self-supervised Learning"
- Balestriero & LeCun (2024) JEPA lecture series