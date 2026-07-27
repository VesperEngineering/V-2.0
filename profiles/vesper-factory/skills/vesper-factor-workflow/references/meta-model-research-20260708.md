# Meta-Model / Stacking Research — Three-Agent Findings (2026-07-08)

## Agent 1: Renaissance Technologies Architecture

Rentec does NOT use a conventional "ensemble of sub-models + meta-model voting layer." They pioneered a **single monolithic constrained optimization** into which all signals feed as inputs.

**Layer 1 — Signal Generation**: hundreds of signals across multiple time horizons (mean reversion, trend, pairs, HMM states, NL kernel regression, NLP sentiment)

**Layer 2 — Portfolio Construction**: unified optimization jointly considering alphas, risk, costs, factor exposures, and interactions. No separate "vote" — the portfolio optimizer IS the meta-model.

**Layer 3 — Risk Management**: strict leverage caps, sector/vol constraints, execution-cost modeling

**Key principle**: "There is no single best signal." The meta-layer decides positioning in real-time based on aggregate signal conviction + risk constraints. The combination method matters more than the signals themselves.

## Agent 2: ML Stacking Methods for Quant Finance

**Ranking by suitability for Vesper (low factor count, 500 stocks)**:

1. **ElasticNet/Ridge meta-model** — simplest stacking approach. Combine base factor scores with non-negative coefficients, walk-forward retrained quarterly. Captures time-varying importance without overfitting. Recommended as starting point.

2. **XGBoost/LightGBM** — state-of-the-art for tabular data. Captures nonlinear interactions. But requires 50+ features to outperform linear models. Overkill at our scale.

3. **Full stacking** (diverse base learners → meta-learner) — best performance in Gu-Kelly-Xiu (2020) but requires many factors, careful walk-forward, and months of tuning.

**When stacking adds value**: high-dimensional factors (50+), complex nonlinear interactions, regime-dependent factor importance, factor redundancy (correlated signals). **When it doesn't**: low-dimensional (3-8 factors), linear relationships dominate, small ticker universe (<1000), short backtest history.

**Implementation requirements**: strict walk-forward (no look-ahead), non-negative coefficients to prevent cancellation, quarterly retraining on 5yr windows.

## Agent 3: Vesper-Specific Architecture

Wrote `docs/meta_model_architecture.md` — concrete blueprint with:
- 3 sub-models at different horizons (5-10d micro, 21d blend, 42-63d macro)
- Regime detector (HMM or rule-based)
- XGBoost meta-learner with ~25 interaction features
- Walk-forward training (2005-2020 train, 2021-2023 validate, 2024-2026 test)
- ~23h implementation, 800 new lines, 3 pip deps

## Convergence Verdict (Parent Agent)

The three agents agree: **meta-model is the right direction but premature.** At 3 validated factors with 245 training observations, an ElasticNet will rediscover the linear weights we already have. The biggest improvement found today wasn't a new combination method — it was rev_10d at IC IR +0.17 (a new signal).

**Decision**: build the meta-model when we have 15+ factors. Until then, signal quality dominates.
