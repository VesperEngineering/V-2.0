# VESPER Model Iteration Log

Research-only regularization experiments. No candidate artifact in this log is deployment-ready.

| Run | Variant | Train IC | OOS IC | OOS Δ vs baseline | Rank IC | Mean top-bottom spread | Spread Δ vs baseline | Verdict |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | `n_estimators=30`, `max_depth=2`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=10.0`, `reg_lambda=30.0` | 0.040195 | 0.032413 | +0.000013 | 0.031414 | 0.002984 | +0.000383 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed. Active trainer/model restored to baseline. |

## Run 1 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_01_train.log`
- Ranking diagnostic: `reports/model_iteration_run_01_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `9d9f20408b78434357e5e195bd3be8164b9dde3ae44787c062576687aeffffff`
- Accepted baseline remains: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 2 | `n_estimators=20`, `max_depth=2`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=10.0`, `reg_lambda=30.0` | 0.039099 | 0.031455 | -0.000945 | 0.032377 | 0.002633 | +0.000033 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed. Active trainer/model restored to baseline. |

| 3 | `n_estimators=40`, `max_depth=2`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=10.0`, `reg_lambda=30.0` | 0.041172 | 0.031992 | -0.000408 | 0.031626 | 0.002403 | -0.000198 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed (minimum 0.002401). Active trainer/model restored to baseline. |

## Run 3 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_03_train.log`
- Ranking diagnostic: `reports/model_iteration_run_03_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `0bb87d30eaab92a68d132ca70369f4b8ab7b538d7109c4da9c078b55003ceb87`
- Accepted baseline remains: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 4 | n_estimators=50, max_depth=2, learning_rate=0.05, subsample=0.6, colsample_bytree=0.6, reg_alpha=10.0, reg_lambda=30.0 | 0.042874 | 0.032196 | -0.000204 | 0.032385 | 0.002269 | -0.000332 | **REJECTED** — OOS IC did not meet baseline +0.003 gate (minimum 0.035400); spread also fell below the minimum 0.002401. Active trainer/model restored to baseline. |

## Run 4 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: reports/model_iteration_run_04_train.log
- Ranking diagnostic: reports/model_iteration_run_04_ranking.json (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: b5b138ea5624cc8f6029af6ced2397b5bd5661f14982d326d881b02202a984ca
- Accepted baseline remains: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 5 | `n_estimators=50`, `max_depth=1`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=20.0` | 0.034567 | 0.032768 | +0.000368 | 0.036038 | 0.005398 | +0.002797 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed. Active trainer/model restored to baseline. |

## Run 5 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_05_train.log`
- Ranking diagnostic: `reports/model_iteration_run_05_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `76baca0b058f0a1c8bfab483aecaf7296233d6127c190069943198768d9f92ec`
- Candidate: train IC 0.034567; OOS IC 0.032768 (+0.000368 versus accepted baseline); rank IC 0.036038; spread 0.005398 (+0.002797).
- Accepted baseline remains: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 6 | n_estimators=40, max_depth=1, learning_rate=0.05, subsample=0.6, colsample_bytree=0.6, reg_alpha=5.0, reg_lambda=20.0 | 0.033728 | 0.032721 | +0.000321 | 0.036399 | 0.007050 | +0.004449 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed. Active trainer/model restored to baseline. |

## Run 6 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: reports/model_iteration_run_06_train.log
- Ranking diagnostic: reports/model_iteration_run_06_ranking.json (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: 71add4647ce379629b161a7129dad144ff9bede17ffa636715f26ab4b0161769
- Candidate: train IC 0.033728; OOS IC 0.032721 (+0.000321 versus accepted baseline); rank IC 0.036399; spread 0.007050 (+0.004449).
- Accepted baseline remains: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 7 | `n_estimators=30`, `max_depth=1`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=20.0` | 0.033279 | 0.033127 | +0.000727 | 0.037192 | 0.006512 | +0.003911 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed. Active trainer/model restored to baseline. |

## Run 7 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_07_train.log`
- Ranking diagnostic: `reports/model_iteration_run_07_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `1851ee64b2238262bf46060045b0185adbcd84c61af77a7901595905913a6e37`
- Candidate: train IC 0.033279; OOS IC 0.033127 (+0.000727 versus accepted baseline); rank IC 0.037192; spread 0.006512 (+0.003911).
- Acceptance gate: OOS minimum 0.035400 failed; spread minimum 0.002401 passed.
- Active trainer/model/metadata restored byte-for-byte to the accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 8 | `n_estimators=20`, `max_depth=1`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=20.0` | 0.031966 | 0.031836 | -0.000564 | 0.040818 | 0.005664 | +0.003064 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed. Active trainer/model/metadata restored byte-for-byte to baseline. |

## Run 8 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_08_train.log`
- Ranking diagnostic: `reports/model_iteration_run_08_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `3e4ef9cec26bdd876f210e9ff5dc19b0ac67131871cdd8738d1e45d63fb5e55e`
- Candidate: train IC 0.031966; OOS IC 0.031836 (-0.000564 versus accepted baseline); rank IC 0.040818; spread 0.005664 (+0.003064).
- Acceptance gate: OOS minimum 0.035400 failed; spread minimum 0.002401 passed.
- Active trainer/model/metadata restored byte-for-byte to the accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 9 | `n_estimators=10`, `max_depth=1`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=20.0` | 0.030758 | 0.033631 | +0.001231 | 0.021110 | 0.000021 | -0.002580 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread also fell below the minimum 0.002401. Active trainer/model/metadata restored byte-for-byte to baseline. |

## Run 9 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_09_train.log`
- Ranking diagnostic: `reports/model_iteration_run_09_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `90ea6883ac6373cf35842eb472b2055da66e6c9aef059f6c22a3cf05d697beb0`
- Candidate: train IC 0.030758; OOS IC 0.033631 (+0.001231 versus accepted baseline); rank IC 0.021110; spread 0.000021 (-0.002580).
- Acceptance gate: OOS minimum 0.035400 failed; spread minimum 0.002401 failed.
- Active trainer/model/metadata restored byte-for-byte to the accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 10 | `n_estimators=25`, `max_depth=1`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=20.0` | 0.032685 | 0.032816 | +0.000416 | 0.038947 | 0.006683 | +0.004082 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed. Active trainer/model/metadata restored byte-for-byte to baseline. |

## Run 10 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_10_train.log`
- Ranking diagnostic: `reports/model_iteration_run_10_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `a19f7dc5aa3351f76ad48885aa23a9c3366725c5965ff953b36a7e26f50308ad`
- Candidate: train IC 0.032685; OOS IC 0.032816 (+0.000416 versus accepted baseline); rank IC 0.038947; spread 0.006683 (+0.004082).
- Acceptance gate: OOS minimum 0.035400 failed; spread minimum 0.002401 passed.
- Active trainer/model/metadata and candidate-specific test expectations restored byte-for-byte to the accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 11 | `n_estimators=35`, `max_depth=1`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=20.0` | 0.033308 | 0.033218 | +0.000818 | 0.036735 | 0.006106 | +0.003505 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed. Active trainer/model/metadata and candidate-specific test expectations restored to baseline. |

## Run 11 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_11_train.log`
- Ranking diagnostic: `reports/model_iteration_run_11_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `2bcd70fa4ef310c2a432633e64e4627484538a2e7a68fb8a475bc701e3088f73`
- Candidate: train IC 0.033308; OOS IC 0.033218 (+0.000818 versus accepted baseline); rank IC 0.036735; spread 0.006106 (+0.003505).
- Acceptance gate: OOS minimum 0.035400 failed; spread minimum 0.002401 passed.
- Active trainer/model/metadata and candidate-specific test expectations restored byte-for-byte to the accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 12 | `n_estimators=30`, `max_depth=1`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=10.0`, `reg_lambda=30.0` | 0.033281 | 0.033125 | +0.000725 | 0.037192 | 0.006512 | +0.003911 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed. Active trainer/model/metadata restored byte-for-byte to baseline. |

## Run 12 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_12_train.log`
- Ranking diagnostic: `reports/model_iteration_run_12_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `db5af68f24e699b545fa874c295128da5961f0c1e119a746aafd1ee1b2184c31`
- Candidate: train IC 0.033281; OOS IC 0.033125 (+0.000725 versus accepted baseline); rank IC 0.037192; spread 0.006512 (+0.003911).
- Acceptance gate: OOS minimum 0.035400 failed; spread minimum 0.002401 passed.
- Active trainer/model/metadata and candidate-specific test expectations restored byte-for-byte to the accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 13 | `n_estimators=50`, `max_depth=2`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=7.5`, `reg_lambda=25.0` | 0.042998 | 0.032132 | -0.000268 | 0.032705 | 0.002163 | -0.000438 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread fell below the minimum 0.002401. Active trainer/model/metadata and candidate-specific test expectations restored byte-for-byte to baseline. |

## Run 13 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_13_train.log`
- Ranking diagnostic: `reports/model_iteration_run_13_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `9ae378799ca99d88191d7d8ee166fc446a8ee8a95add75ef261a6aa7aba74dde`
- Candidate: train IC 0.042998; OOS IC 0.032132 (-0.000268 versus accepted baseline); rank IC 0.032705; spread 0.002163 (-0.000438).
- Acceptance gate: OOS minimum 0.035400 failed; spread minimum 0.002401 failed.
- Active trainer/model/metadata and candidate-specific test expectations restored byte-for-byte to the accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 14 | n_estimators=50, max_depth=2, learning_rate=0.05, subsample=0.6, colsample_bytree=0.6, reg_alpha=5.0, reg_lambda=30.0 | 0.043311 | 0.032162 | -0.000238 | 0.030355 | 0.002729 | +0.000128 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed. Active trainer/model/metadata and candidate-specific test expectation restored byte-for-byte to baseline. |

## Run 14 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: reports/model_iteration_run_14_train.log
- Ranking diagnostic: reports/model_iteration_run_14_ranking.json (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: 6960ad42e1ed20eed592b81bb44dc81cfb76d55e39e59159f667903c4ed750ac
- Candidate: train IC 0.043311; OOS IC 0.032162 (-0.000238 versus accepted baseline); rank IC 0.030355; spread 0.002729 (+0.000128).
- Acceptance gate: OOS minimum 0.035400 failed; spread minimum 0.002401 passed.
- Active trainer/model/metadata and candidate-specific test expectation restored byte-for-byte to the accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 15 | `n_estimators=45`, `max_depth=1`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=20.0` | 0.034083 | 0.033017 | +0.000617 | 0.034999 | 0.007223 | +0.004623 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed. Active trainer/model/metadata and candidate-specific test expectations restored to baseline. |

## Run 15 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_15_train.log`
- Ranking diagnostic: `reports/model_iteration_run_15_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `a7dc0e9e6b2da91808881904a8f062109406d01bab7896c91d114d321ff9b694`
- Candidate: train IC 0.034083; OOS IC 0.033017 (+0.000617 versus accepted baseline); rank IC 0.034999; spread 0.007223 (+0.004623).
- Acceptance gate: OOS minimum 0.035400 failed; spread minimum 0.002401 passed.
- Active trainer/model/metadata and candidate-specific test expectations restored byte-for-byte to the accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.
| 16 | `n_estimators=45`, `max_depth=2`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=20.0` | 0.042443 | 0.032639 | +0.000239 | 0.029958 | 0.002020 | -0.000581 | **REJECTED** — rejected: out-of-sample IC improvement did not meet the required 0.003 threshold; active trainer, model, metadata, and candidate-specific test expectations restored byte-for-byte from baseline. |

## Run 16 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_16_train.log`
- Ranking diagnostic: `reports/model_iteration_run_16_ranking.json`
- Candidate model SHA-256: `0a46605f4da2477ef4f1f41910aef454a5c45895ef96d8eb279600d1e5d88a40`
- Candidate: train IC 0.042443; OOS IC 0.032639 (+0.000239 versus accepted baseline); rank IC 0.029958; spread 0.002020 (-0.000581).
- Acceptance gates: OOS minimum 0.035400; spread minimum 0.002401 and positive. candidate rejected and baseline restored.

| 17 | n_estimators=50, max_depth=1, learning_rate=0.05, subsample=0.6, colsample_bytree=0.6, reg_alpha=7.5, reg_lambda=25.0 | 0.034567 | 0.032769 | +0.000369 | 0.036067 | 0.005430 | +0.002829 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed. Active trainer/model/metadata and candidate-specific test expectations restored byte-for-byte to baseline. |

## Run 17 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: reports/model_iteration_run_17_train.log
- Ranking diagnostic: reports/model_iteration_run_17_ranking.json (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: 73d3ec6a8138ac9f24d4123d723bc5d6cd336f3971aebbfba5eb5cfc5a41f562
- Candidate: train IC 0.034567; OOS IC 0.032769 (+0.000369 versus accepted baseline); rank IC 0.036067; spread 0.005430 (+0.002829).
- Acceptance gate: OOS minimum 0.035400 failed; spread minimum 0.002401 passed.
- Active trainer/model/metadata and candidate-specific test expectations restored byte-for-byte to accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 18 | `n_estimators=50`, `max_depth=2`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=25.0` | 0.043327 | 0.032154 | -0.000246 | 0.030359 | 0.002729 | +0.000128 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed. Active trainer/model/metadata and candidate-specific test expectation restored byte-for-byte to baseline. |

## Run 18 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_18_train.log`
- Ranking diagnostic: `reports/model_iteration_run_18_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `a2325019d35413ce9a8ee65af9da5b1d5f35705624891713da7eb587c6c961f5`
- Candidate: train IC 0.043327; OOS IC 0.032154 (-0.000246 versus accepted baseline); rank IC 0.030359; spread 0.002729 (+0.000128).
- Acceptance gate: OOS minimum 0.035400 failed; spread minimum 0.002401 and positive passed.
- Active trainer/model/metadata and candidate-specific test expectation restored byte-for-byte to accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 19 | `n_estimators=50`, `max_depth=1`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=10.0`, `reg_lambda=30.0` | 0.034567 | 0.032769 | +0.000369 | 0.036061 | 0.005430 | +0.002829 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed. Active trainer/model/metadata and candidate-specific test expectations restored byte-for-byte to baseline. |

## Run 19 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_19_train.log`
- Ranking diagnostic: `reports/model_iteration_run_19_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `51d9f9a5acc3bb47ba7160fc6bf2a30645b5beeb879b7e36cce463f465f7e12a`
- Candidate: train IC 0.034567; OOS IC 0.032769 (+0.000369 versus accepted baseline); rank IC 0.036061; spread 0.005430 (+0.002829).
- Acceptance gate: OOS minimum 0.035400 failed; positive spread minimum 0.002401 passed.
- Active trainer/model/metadata and candidate-specific test expectations restored byte-for-byte to accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 20 | `n_estimators=50`, `max_depth=2`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=40.0` | 0.042952 | 0.032013 | -0.000387 | 0.032332 | 0.001531 | -0.001070 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread fell below the minimum 0.002401. Active trainer/model/metadata and candidate-specific test expectation restored byte-for-byte to baseline. |

## Run 20 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_20_train.log`
- Ranking diagnostic: `reports/model_iteration_run_20_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `8e6411bced18601aa04933def69be03625c8a1478718d7c76167062991f0a339`
- Candidate: train IC 0.042952; OOS IC 0.032013 (-0.000387 versus accepted baseline); rank IC 0.032332; spread 0.001531 (-0.001070).
- Acceptance gates: OOS minimum 0.035400; positive spread minimum 0.002401; both failed.
- Active trainer/model/metadata and candidate-specific test expectation restored byte-for-byte to accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 21 | `n_estimators=40`, `max_depth=2`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=20.0` | 0.041483 | 0.032243 | -0.000157 | 0.029921 | 0.001675 | -0.000926 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread fell below the minimum 0.002401. Active trainer/model/metadata and candidate-specific test expectations restored byte-for-byte to baseline. |

## Run 21 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_21_train.log`
- Ranking diagnostic: `reports/model_iteration_run_21_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `57af8e8a4646b8d8c5ddf84d28fd6ee764a7859d11faaa28f305b2801a8be24e`
- Candidate: train IC 0.041483; OOS IC 0.032243 (-0.000157 versus accepted baseline); rank IC 0.029921; spread 0.001675 (-0.000926).
- Acceptance gates: OOS minimum 0.035400; positive spread minimum 0.002401; both failed.
- Active trainer/model/metadata and candidate-specific test expectations restored byte-for-byte to accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.
| 22 | `n_estimators=50`, `max_depth=2`, `learning_rate=0.05`, `subsample=0.5`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=20.0` | 0.043038 | 0.031595 | -0.000805 | 0.034511 | 0.002948 | +0.000348 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed. Active trainer/model/metadata and candidate-specific test expectation restored byte-for-byte to baseline. |

## Run 22 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_22_train.log`
- Ranking diagnostic: `reports/model_iteration_run_22_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `dafa36488121a34b519f066fd12804fa4c0629c925f104f8c2583f3484616a94`
- Candidate: train IC 0.043038; OOS IC 0.031595 (-0.000805 versus accepted baseline); rank IC 0.034511; spread 0.002948 (+0.000348).
- Acceptance gate: OOS minimum 0.035400 failed; spread minimum 0.002401 passed.
- Active trainer/model/metadata and candidate-specific test expectation restored byte-for-byte to accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 23 | `n_estimators=50`, `max_depth=2`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.5`, `reg_alpha=5.0`, `reg_lambda=20.0` | 0.042687 | 0.031899 | -0.000501 | 0.032242 | 0.002433 | -0.000168 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed. Active trainer/model/metadata and candidate-specific test expectation restored byte-for-byte to baseline. |

## Run 23 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_23_train.log`
- Ranking diagnostic: `reports/model_iteration_run_23_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `eadbc871a6ac7f7c34d2e487d95cb67264b7ce7fa852856ffdf26ff0c9c2dd93`
- Candidate: train IC 0.042687; OOS IC 0.031899 (-0.000501 versus accepted baseline); rank IC 0.032242; spread 0.002433 (-0.000168).
- Acceptance gate: OOS minimum 0.035400 failed; positive spread minimum 0.002401 passed.
- Active trainer/model/metadata and candidate-specific test expectation restored byte-for-byte to accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.


| 24 | `n_estimators=50`, `max_depth=2`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=20.0`, `min_child_weight=5.0` | 0.043278 | 0.032371 | -0.000029 | 0.030778 | 0.002601 | +0.000000 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); spread gate passed. Active trainer/model/metadata and candidate-specific test expectation restored byte-for-byte to baseline. |

## Run 24 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_24_train.log`
- Ranking diagnostic: `reports/model_iteration_run_24_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `e39e7bab699aef4d5623df16e53ef393163f5ede9daa118315fd376eb9a5b4c5`
- Candidate: train IC 0.043278; OOS IC 0.032371 (-0.000029 versus accepted baseline); rank IC 0.030778; spread 0.002601 (+0.000000).
- Acceptance gate: OOS minimum 0.035400 failed; positive spread minimum 0.002401 passed.
- Active trainer/model/metadata and candidate-specific test expectation restored byte-for-byte to accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 25 | `n_estimators=50`, `max_depth=2`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=20.0`, `min_child_weight=10.0` | 0.043278 | 0.032371 | -0.000029 | 0.030778 | 0.002601 | +0.000000 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); candidate hash matched baseline. Active trainer/model/metadata and test expectation restored byte-for-byte to baseline. |

## Run 25 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_25_train.log`
- Ranking diagnostic: `reports/model_iteration_run_25_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `e39e7bab699aef4d5623df16e53ef393163f5ede9daa118315fd376eb9a5b4c5` (identical to accepted baseline).
- Candidate: train IC 0.043278; OOS IC 0.032371 (-0.000029 versus accepted baseline); rank IC 0.030778; spread 0.002601 (+0.000000).
- Acceptance gate: OOS minimum 0.035400 failed; positive spread minimum 0.002401 passed.
- Active trainer/model/metadata and candidate-specific test expectation restored byte-for-byte to accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

| 26 | `n_estimators=50`, `max_depth=2`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=20.0`, `gamma=1.0` | 0.043278 | 0.032371 | -0.000029 | 0.030778 | 0.002601 | +0.000000 | **REJECTED** — OOS IC did not meet the required baseline +0.003 gate (minimum 0.035400); candidate hash matched baseline. Active trainer/model/metadata restored byte-for-byte to baseline. |

## Run 26 evidence

- Protocol unchanged: 5-session label, 24 features, chronological split at 2021-01-01, fixed seed 42, and local split-adjusted Massive data.
- Training: `reports/model_iteration_run_26_train.log`
- Ranking diagnostic: `reports/model_iteration_run_26_ranking.json` (80 evaluation dates; 10-name top/bottom baskets)
- Candidate model SHA-256: `e39e7bab699aef4d5623df16e53ef393163f5ede9daa118315fd376eb9a5b4c5` (identical to accepted baseline).
- Candidate: train IC 0.043278; OOS IC 0.032371 (-0.000029 versus accepted baseline); rank IC 0.030778; spread 0.002601 (+0.000000).
- Acceptance gate: OOS minimum 0.035400 failed; positive spread minimum 0.002401 passed.
- Active trainer/model/metadata and candidate-specific test expectation restored byte-for-byte to accepted baseline: OOS IC 0.032400, rank IC 0.030778, spread 0.002601.

## Run 27 — REJECTED

- Hypothesis: add `max_delta_step=1.0` while holding the accepted baseline capacity, sampling, and L1/L2 penalties fixed.
- Parameters: `n_estimators=50`, `max_depth=2`, `learning_rate=0.05`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=20.0`, `max_delta_step=1.0`.
- Candidate: train IC 0.043278363663; OOS IC 0.032370512827; rank IC 0.030777552902; top-bottom spread 0.002600822136; SHA-256 `e9e74b657ca4c1060aec65dbbb9f84197a61e558c6b027d3d89375daa97e04be`.
- Baseline comparison: OOS IC delta -0.000029487173 (required >= 0.003000000000); spread delta 0.000000000000 (floor 0.002400822136).
- Verdict: rejected; OOS IC gate failed. Active trainer, model, and metadata were restored from baseline before finalization. Research only; no deployment or execution claim.
- Artifacts: `reports/model_iteration_run_27_train.log`, `reports/model_iteration_run_27_ranking.json`, `reports/model_iteration_run_27_ranking.log`.

## Run 28 — REJECTED

- Hypothesis: reduce row subsampling from `0.6` to `0.5` while holding the accepted baseline capacity, depth, column sampling, and L1/L2 penalties fixed.
- Parameters: `n_estimators=50`, `max_depth=2`, `learning_rate=0.05`, `subsample=0.5`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=20.0`.
- Candidate: train IC 0.043037596984; OOS IC 0.031594944214; rank IC 0.034511303493; top-bottom spread 0.002948459506; SHA-256 `dafa36488121a34b519f066fd12804fa4c0629c925f104f8c2583f3484616a94`.
- Baseline comparison: OOS IC delta -0.000805055786 (required >= 0.003000000000); spread delta +0.000347637370 (floor 0.002400822136).
- Verdict: rejected; OOS IC gate failed. Candidate reproduced the run-22 artifact/metrics. Active trainer, model, metadata, and test expectation were restored from baseline before finalization. Research only; no deployment or execution claim.
- Artifacts: `reports/model_iteration_run_28_train.log`, `reports/model_iteration_run_28_ranking.json`, `reports/model_iteration_run_28_ranking.log`.


## Run 29 — REJECTED

- Hypothesis: hold accepted tree capacity, depth, sampling, and L1/L2 penalties fixed while setting min_child_weight=2.0.
- Parameters: n_estimators=50, max_depth=2, learning_rate=0.05, subsample=0.6, colsample_bytree=0.6, reg_alpha=5.0, reg_lambda=20.0, min_child_weight=2.0.
- Candidate: train IC 0.043278363663; OOS IC 0.032370512827; rank IC 0.030777552902; top-bottom spread 0.002600822136; SHA-256 e39e7bab699aef4d5623df16e53ef393163f5ede9daa118315fd376eb9a5b4c5 (identical to accepted baseline).
- Baseline comparison: OOS IC delta -0.000029487173 (required >= 0.003000000000); spread delta +0.000000000000 (floor 0.002400822136).
- Verdict: rejected; OOS IC gate failed. Active trainer, model, metadata, and candidate-specific test expectation restored from baseline before finalization. Research only; no deployment or execution claim.
- Artifacts: reports/model_iteration_run_29_train.log, reports/model_iteration_run_29_ranking.json, reports/model_iteration_run_29_ranking.log.

## Run 30 — REJECTED

- Hypothesis: hold accepted tree count, depth, sampling, and L1/L2 penalties fixed while reducing `learning_rate` from `0.05` to `0.04`.
- Parameters: `n_estimators=50`, `max_depth=2`, `learning_rate=0.04`, `subsample=0.6`, `colsample_bytree=0.6`, `reg_alpha=5.0`, `reg_lambda=20.0`.
- Candidate: train IC 0.042011309061; OOS IC 0.032107313938; rank IC 0.032856996060; top-bottom spread 0.002895056126; SHA-256 `cbe1167c23741468db8c602062c2774dc38b8218a0105705e0b44110330a4f68`.
- Baseline comparison: OOS IC delta -0.000292686062 (required >= 0.003000000000); spread delta +0.000294233990 (floor 0.002400822136).
- Verdict: rejected; OOS IC gate failed. Active trainer, model, metadata, and candidate-specific test expectation restored from baseline before finalization. Research only; no deployment or execution claim.
- Artifacts: `reports/model_iteration_run_30_train.log`, `reports/model_iteration_run_30_ranking.json`, `reports/model_iteration_run_30_ranking.log`.
