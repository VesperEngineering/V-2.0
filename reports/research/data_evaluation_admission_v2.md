# V20 post-repair data and evaluation re-audit v2

**Audit time:** 2026-07-27T02:17:05Z  
**Scope:** Read-only re-audit of the frozen SPY CPU selection contract, frozen adapter, current repaired evaluator/tests, and prior admission/review/plan evidence. No code, data, configuration, model, schedule, credential, provider, broker, risk, execution, or external system was changed; no outcomes were computed.

## Decision

**HOLD** for the frozen CPU experiment contract. The bounded evaluator repair is verified, and the frozen SPY adapter retains the previously admitted development/selection data properties. However, the exact contract that was frozen before the repair is not compatible with the current fail-closed evaluator and cannot reach an integrity receipt. It also cannot admit a final holdout: the available adapter ends 2026-06-30 and carries only an `ADMIT_SELECTION` receipt.

Green evaluator tests do not cure either blocker.

## Evidence

### Current repaired evaluator: verified, but bounded

- Current hashes measured at audit time:
  - `scripts/spy_momentum_cpu_experiment.py`: `bc9b88293021447c527ae3256b9723ec14ff2707c384f155603ab08e88b5e4c8`
  - `tests/test_spy_momentum_cpu_experiment.py`: `f7ab005b60bd52ce944fa00dfbebba44d61e544a1652bf284534b1963eda5191`
  - `reports/research/spy_momentum_cpu_slice2_remediation_provenance_v5.json`: `a04013dc22f14de53ddcc92de106a123c802064e917e094aa1e7f056fc6430b0`
- Those evaluator/test bytes match the V5 provenance `after` mapping. `reports/research/spy_momentum_cpu_slice2_remediation_review_v5.md` independently records bounded acceptance of full label-interval partition checks, source-availability/freezing checks, pre-receipt rehashing, deterministic receipt binding, and fail-closed selection/final authority.
- Fresh focused verification passed:

  ```text
  python -m pytest tests/test_spy_momentum_cpu_experiment.py -q --basetemp=<temporary path>
  43 passed in 34.27s
  ```

- Fresh `python -m py_compile scripts/spy_momentum_cpu_experiment.py tests/test_spy_momentum_cpu_experiment.py` and `git diff --check -- scripts/spy_momentum_cpu_experiment.py tests/test_spy_momentum_cpu_experiment.py reports/research/spy_momentum_cpu_slice2_remediation_provenance_v5.json` both exited 0.
- This evidence validates the code-side fail-closed mechanism only. It does not itself admit data, approve a phase, enable the absent selection anchor, open final evaluation, or establish a future holdout.

### Frozen adapter: retained read-only selection-data evidence

- Adapter: `vesper/data/massive/adapters/total_return_ohlcv_adapter_20260717T153500Z.sqlite`
- Fresh SHA-256: `825252f94efb228df37683d58a1199cbc101828bbe7f53079e9d066c28e5a70c`, matching `reports/research/spy_momentum_cpu_slice3_data_admission_v1.json` and the V5 provenance.
- Read-only SQLite inspection found adapter metadata:

  ```text
  price_basis=total_return_adjusted
  timeframe=1day
  generated_at=2026-07-17T15:39:01.593969+00:00
  source_table=total_return_adjusted_day_aggs
  ```

- SPY has 5,737 rows and 5,737 distinct timestamps; all required OHLC values are finite and positive. Its source map also has 5,737 rows, with zero missing `source_ticker`, `source_as_of_date`, `source_key`, or `source_sha256` values. The observed SPY session and source-as-of range is 2003-09-10 through 2026-06-30.
- `reports/research/spy_momentum_cpu_slice3_data_admission_v1.json` remains correctly scoped as `ADMIT_SELECTION`, explicitly excluding final-holdout admission and raw-to-derived V20-local reconstruction. The prior plan's SPY-only scope avoids the broad fixed-502 point-in-time-universe claim; it does not validate the broad model path.

### Frozen contract cannot pass current integrity validation

- Exact contract: `reports/research/spy_momentum_cpu_contract_v2.json`, SHA-256 `7fb4f6e600d5431749f2eca9f3a8851b8a6c564db30c56da6ca22c615931aeb8`.
- The current evaluator's read-only selection integrity invocation against those exact bytes exited 1 before producing stdout:

  ```text
  ValueError: contract availability freeze required
  ```

- The contract predates the repaired evaluator and lacks the now-required `freeze.availability_freeze`; its stored evaluator hash is also the superseded `2d01b7214ae775176132190c72a7dec07544edb8caac6ab84abc189f07b7dd75`, not the current evaluator hash above.
- Independently of that first failure, the frozen contract does not meet the repaired complete-chronology shape: it declares cadence 6 while the current evaluator requires five-session cadence, and it has no `final_from`. The current selection approval anchor is intentionally `None`, so selection remains fail-closed even if a compliant contract were supplied.

## Blockers

1. **Exact frozen-contract blocker:** no current, checksummed replacement contract binds the repaired evaluator hash, immutable availability freeze, required five-session chronological declarations, and the admitted adapter. Altering the old JSON would create a new contract, not validate the frozen one; it requires the approved contract/review process.
2. **Final data-admission blocker:** no independently admitted genuinely future sealed SPY snapshot exists. The frozen adapter ends 2026-06-30, the prior receipt is selection-only, and it lacks a future source/receipt/revision lineage plus at least 52 completed non-overlapping final labels. Historical adapter rows cannot substitute for final data.
3. **Authority blocker:** the selection approval anchor remains absent and final evaluation retains its external-approval failure. These are intended controls, not defects to bypass.
4. **Scope limitation:** the adapter is a frozen derived total-return research input. It remains reproducible from local bytes but not raw-to-derived reconstructible from a complete V20-local source package; it cannot admit the broad 502-name model experiment.

## Next owner

**Brennan/Product:** decide whether to authorize replacement of the invalidated selection contract against the repaired evaluator and route that contract/review work through the established admission process. A data steward must separately provide a future immutable SPY snapshot and lineage package before any final-holdout admission. Quant Research may only run a selection evaluation after a new contract is independently admitted and the required selection authority exists; neither selection nor final outcomes are authorized by this report.

HOLD
