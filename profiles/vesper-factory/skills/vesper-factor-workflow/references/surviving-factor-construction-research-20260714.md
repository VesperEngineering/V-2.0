# Surviving Factor Performance — Alternative Construction Methods

**Date:** 2026-07-14 | **Author:** Rez (single dispatch research rez)

## Context

Vesper had only 2/16 factors surviving Fama-MacBeth validation (|t| > 2.0). This reference summarizes the research findings on alternative factor construction methods to improve factor survival rates. Full document: `artifacts/evals/research_rez_20260714.md`.

## Key Findings

### 1. Higher-Order & Interaction Factors (Borri et al. 2025, arXiv:2503.23501)
- Squares (f²), cubes (f³), and pairwise products (fᵢ×fⱼ) of common linear factors are **significantly priced** in the cross-section
- Many zoo factors' pricing power is attributable to higher-order term exposure
- **Action:** Construct interaction factors from surviving survivors + dead factors; run FM on the expanded set

### 2. ML on Factor Residuals (Feng et al. 2018, arXiv:1805.01104)
- Autoencoder factor models compress 16+ factors → 3-5 latent factors capturing non-linear interactions
- Deep factor models with hidden-layer latent factors outperform characteristic-sorted factors
- **Action:** Orthogonalize dead factors against surviving ones; test residuals for orthogonal alpha

### 3. Conditional Sorting / Dependent Double Sorting
- A factor that fails unconditionally may work within size or volatility subgroups
- Size-conditioned factor construction (within market-cap quintiles) improves t-stats
- **Action:** Re-run FM within size quintiles for each dead factor

## Implementation Priority

| Phase | Action | Difficulty | Expected Impact |
|-------|--------|------------|-----------------|
| 1 | Interaction factors (S₁×Dᵢ, S₂×Dᵢ) | Minimal code | 3-5 new survivors |
| 1 | Residual orthogonalization | Minimal code | 1-2 new survivors |
| 1 | Size-conditioned FM re-evaluation | Analysis only | Identify salvageable factors |
| 2 | Autoencoder latent factors | 1-2 weeks | 3-5 latent factors |
| 2 | Forward selection FM (Borri procedure) | 1-2 weeks | Most rigorous interaction test |
| 3 | Conditional factor models | Ongoing | Time-varying beta capture |

## Source Papers

- Borri, Chetverikov, Liu & Tsyvinski (2025). *Higher-Order Asset Pricing Factors via Forward Selection Fama-MacBeth Regression*. arXiv:2503.23501
- Feng, He, Polson & Xu (2018). *Deep Learning in Characteristics-Sorted Factor Models*. arXiv:1805.01104
- Ye, Goswami, Gu, Uddin & Wang (2024). *From Factor Models to Deep Learning: ML in Reshaping Empirical Asset Pricing*. arXiv:2403.06779
- *Mining the Factor Zoo: Estimation of Latent Factor Models with Sufficient Proxies*. arXiv:2212.12845
- *Semiparametric Conditional Factor Models in Asset Pricing*. arXiv:2112.07121
- *Robust Estimation of Conditional Factor Models*. arXiv:2204.00801
- *The Co-Pricing Factor Zoo*. arXiv:2604.04430