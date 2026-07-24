# V20 independent data-admission review v1

**Review classification:** **PARTIAL**  
**Underlying admission decision:** **NO-GO remains supported**  
**Review time:** 2026-07-23 UTC  
**Scope:** Independent review of `reports/research/data_evaluation_admission_v1.md` using read-only V20 evidence under `C:/Users/bgonn/Desktop/v20`. No code, data, configuration, model, schedule, broker, provider, or GPU state was changed, and no training was executed.

## Decision

The admission report is directionally correct and its NO-GO decision remains supported by independent blockers in universe construction, availability/lineage, purge/embargo, and holdout independence. It is not fully validated because its decisive adjustment-basis account is materially incomplete and partly contradicted by the actual V20 receipts:

- the primary 502-name SQLite table is raw and the V20 checkout has no local `split_adjustments.json`;
- however, the trainer is not shown falling back to raw prices in the recorded experiments: all 30 training receipts report loading `D:\vesper\vesper_data\split_adjustments.json` and applying adjustments to 502 tickers;
- V20 also contains a local total-return adapter with row-level source hashes and build metadata, although it covers only a 31-name alias-normalized validation subset and is not the configured 502-name trainer input.

The receipts do not establish that the external split map was correct, immutable, or bound by checksum to the model runs. Therefore the broad experiment still lacks an admissible, self-contained adjustment contract, but the report's claim that the historical/current training path used raw prices is rejected as written.

## Evidence reviewed

- Governance: `AGENTS.md:58-74`; V20 risk-review SOUL; `quant workers/vesper-financial-risk-management/SKILL.md:18-27,56-66`.
- Admission report: `reports/research/data_evaluation_admission_v1.md`.
- Primary source and clocks: `config/settings.yaml:21-28`; `vesper/data/feed.py:124-166`; `vesper/data/features.py:32-136`; `scripts/train_model.py:27-76,95-147,208-239`; `config/universe.yaml`.
- Research-source labeling: `scripts/intermediate_momentum_research.py:12-24,194-225`.
- Actual receipts: `reports/model_iteration_run_01_train.log`, `reports/model_iteration_run_30_train.log`, all intervening run logs, `reports/model_iteration_state.json`, `reports/model_iteration_log.md`, `reports/model_iteration_run_01_ranking.json`, `reports/model_iteration_run_30_ranking.json`, `models/xgb_ranker.metadata.json`, and `reports/portfolio_ablation_2026-07-22.md`.
- Local adjustment/lineage evidence inspected read-only: `vesper/data/massive/adapters/total_return_ohlcv_adapter_20260717T153500Z.sqlite`, `vesper/data/massive/total_return/day_aggs_total_return_adjusted_active_universe_20260717T153500Z.sqlite`, and `vesper/data/massive/governance/total_return_universe_membership_20260717T153500Z.sqlite`.
- No standalone frozen CPU experiment contract was cited or found. The review therefore tests the report's stated admission standard and the recorded chronological protocol, not an independently frozen experiment contract.

## Decisive-finding review

| Decisive finding | Review result | Independent evidence and challenge | Admission effect |
|---|---|---|---|
| Adjustment basis | **REJECTED AS WRITTEN / blocker remains** | `MassiveFeed` selects raw OHLCV (`vesper/data/feed.py:147-161`), and no V20-local `split_adjustments.json` exists. But `_load_split_adjustments` also searches `D:/vesper/vesper_data/split_adjustments.json` (`scripts/train_model.py:44-58`). Run 1 and run 30 receipts each state that this D: map was loaded and applied to 502 tickers (`reports/model_iteration_run_01_train.log:1-9`; `reports/model_iteration_run_30_train.log:1-9`); the same messages are present in all 30 run logs. Separately, the local adapter database contains 169,556 daily rows for 31 tickers, declares `price_basis=total_return_adjusted`, and maps rows to source keys and SHA-256 values. The source total-return database covers 33 tickers, not the broad 502-name trainer universe. | Historical runs were receipt-labeled split-adjusted, not raw fallback. Nevertheless, factor correctness, version, checksum binding, and reproducibility are not evidenced within the 502-name V20 contract, and the 31/33-name total-return assets cannot substitute for broad research. |
| Point-in-time universe | **VERIFIED** | Read-only inspection of `sp500_ohlcv.sqlite` found one table, 2,482,807 rows, and 502 distinct tickers. The trainer loads every ticker in that table (`scripts/train_model.py:79-92`); no membership date is joined. `config/universe.yaml` is a static list with no effective dates. The research code explicitly labels the source `fixed-502-universe` and `survivorship-limited` (`scripts/intermediate_momentum_research.py:12-24,218-224`). The local governance database contains only six alias/lifecycle membership records and therefore does not provide historical constituent membership for the broad 502-name universe. | The existing broad cross-sectional evaluation remains survivorship-limited and inadmissible as point-in-time S&P 500 research. |
| Availability and lineage | **VERIFIED, with omitted subset evidence** | Primary SQLite inspection found only `sp500_ohlcv(ticker,date,close,volume,open,high,low)`: no publication time, receipt time, revision identifier, source key, or source hash. It had 2,482,807 rows, 502 tickers, zero duplicate ticker/date groups, dates 2003-09-10 through 2026-07-21, 502 rows on the latest date, mtime 2026-07-22T22:42:38.856210Z, and no matching `20260721`/`20260722` source file, manifest, or `.sha256` receipt under the primary `sp500` path. At review time 2026-07-23T13:11:05Z, the 2026-07-22 US session was absent. Same-row close-dependent features, including `intraday_ret`, are computed without an availability-time contract (`vesper/data/features.py:41-126`). The local 31-name adapter does carry source hashes and generated-at metadata, but it is not the primary 502-name input. | Structural coverage is reproducible, but primary-source freshness, revision lineage, and signal-availability timing are not. The subset lineage evidence should have been disclosed but does not cure the primary-source failure. |
| Five-session purge/embargo | **VERIFIED** | Labels are created before the date split as `pct_change(5).shift(-5)` (`scripts/train_model.py:95-147`), while samples are split only on feature date at 2021-01-01 (`scripts/train_model.py:219-225`). No purge or embargo appears in the V20 training path. A read-only SQLite window check found 2,370 source rows across 474 tickers dated 2020-12-24 through 2020-12-31 whose five-session outcome dates fall from 2021-01-04 through 2021-01-08. | Training labels cross into the evaluation period. The existing chronological result is contaminated at the split boundary. |
| Untouched final holdout | **VERIFIED** | The trainer defines only pre-2021 train and post-2021 test periods (`scripts/train_model.py:219-239`). Parsed `reports/model_iteration_state.json` records 30 rejected parameter runs, run IDs 1-30, zero accepted candidates, and the same 1,780,896 train / 673,562 test sample counts for every run. The run receipts repeatedly compare candidate metrics against the same OOS gate; run 1 and run 30 ranking receipts each use 80 evaluation dates. The portfolio ablation explicitly says it is retrospective and not a fresh promotion holdout (`reports/portfolio_ablation_2026-07-22.md:1-16`). | The post-2021 period is model-selection evidence, not an untouched final holdout. No promotion claim may rely on it as independent final evidence. |

## Additional evidence conflicts and unresolved risks

1. **Adjustment receipt versus report:** `reports/research/data_evaluation_admission_v1.md:16,26` says the active path falls back to raw prices and treats historical split-adjustment claims as unverified. The local run receipts consistently say the D: split map was loaded and applied. The receipts verify runtime behavior only; the external factor file itself was outside this review's authorized V20 scope and is not frozen into the local evidence package.
2. **Local subset omitted:** V20 contains a total-return adapter with generated-at metadata, a declared total-return basis, and row-level source hashes. It is limited to 31 alias-normalized names backed by a 33-name source and is not wired into the primary trainer. The admission report should distinguish “not available” from “available only for validation and not admissible for broad research.”
3. **Receipt-count inconsistency:** `models/xgb_ranker.metadata.json:7-8` records 1,780,896 train and 675,562 test samples, while each of the 30 iteration receipts records 1,780,896 train and 673,562 test samples. No frozen source snapshot or revision receipt explains the differing test population.
4. **Feature execution clock unresolved:** The formulas avoid explicit future rows, but same-session close/high/low/volume features are not tied to a declared signal-formation and execution timestamp. Formula direction alone is not proof of deployable availability.
5. **No frozen contract:** There is no independently evidenced contract binding source hashes, adjustment policy, point-in-time membership, feature/label clocks, purge rule, selection period, and final holdout before experimentation.

## Final classification

**PARTIAL.** Four decisive NO-GO findings are independently verified: the broad universe is not point-in-time, primary availability/lineage is insufficient, the five-session boundary is not purged, and the only OOS period has been reused for model selection. The adjustment-basis finding is materially misstated because actual receipts show split adjustments were applied and local total-return subset assets exist. Those receipts still do not establish a frozen, correct, reproducible 502-name adjustment basis, so the underlying **NO-GO remains supported** without relying on the rejected raw-fallback claim.

## One next safe action

Brennan may commission, without this review authorizing execution, a corrected frozen admission package that binds a V20-local checksummed 502-name source and adjustment artifact, point-in-time membership, explicit availability clocks, a five-session purge rule, and disjoint selection/final-holdout periods before any new CPU experiment is run.
