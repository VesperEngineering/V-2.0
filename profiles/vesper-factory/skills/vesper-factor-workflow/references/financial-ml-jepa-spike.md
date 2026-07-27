# Financial ML / JEPA Research Spike Protocol

Reusable discipline for a resource-bounded self-supervised representation-learning experiment over market time series. This is a methodology reference, not evidence of a trading strategy.

## Scope boundary

- Use a standalone experiment folder and its own virtual environment, with copied or read-only input data.
- Do not import production trading modules, alter the production environment or data pipeline, use broker APIs, or write production artifacts.
- Keep three claims distinct: **representation health**, **latent temporal prediction**, and **economic alpha**. Evidence for one does not establish either of the others.

## Experiment ladder

1. **Representation health:** establish non-collapse using per-dimension standard deviation, effective rank, and pairwise cosine similarity.
2. **Temporal prediction:** predict a future latent state and compare against an explicit persistence baseline. A win demonstrates only that the learned state is predictable.
3. **Frozen downstream probe:** freeze the encoder and test a deliberately simple downstream model using a chronological split.
4. **Purged walk-forward comparison:** train every component inside each fold's historical period and compare against an explicit raw-feature/factor baseline.

## Financial time-series safeguards

- Fit ticker-level normalizers solely on observations before each fold's test start.
- Use an embargo that covers both the feature window and forward label horizon whenever testing across a train/test boundary. State the exact session count.
- Exclude a security from a fold if it cannot produce a pre-test scaler and required purged training samples. This is an admission gate, not a missing-value problem.
- Treat warnings, NaNs, empty sample populations, or a broken admission gate as an invalid run. Repair, rerun, then document the result.
- Never apply to an out-of-sample period an encoder that was pretrained on that period.
- Overlapping windows invalidate naïve independence assumptions. Do not promote a small AUC difference without a dependence-aware statistical test and replication across folds.

## GPU resource receipt

- Prove the intended accelerator through a real tensor computation before claiming it is in use.
- Benchmark the actual workload: a tiny network or a small batch can be slower on GPU due to copy and launch overhead.
- Scale batch size only after checking available VRAM. Record device, total/used memory, batch size, epochs, and elapsed runtime.
- Preserve a CPU fallback; validity cannot depend on the accelerator.

## Reporting template

Report each verdict separately:

| Claim | Required evidence | What it does **not** prove |
|---|---|---|
| Architecture | non-collapse metrics | return forecasting or alpha |
| Temporal latent state | beats specified persistence baseline | price/return direction prediction |
| Economic signal | stable, purged walk-forward improvement vs baseline | deployability without FM/Newey-West and promotion gates |

A reproducible negative result is useful. After non-replication, do not tune until something works. Change to a substantively distinct, pre-registered question—such as a cross-sectional ranker tested under Fama–MacBeth/Newey–West.
