# SPY Momentum CPU Slice 2 Fourth Remediation Independent Review v5

## Classification

**Review timestamp:** 2026-07-27T01:57:18Z  
**Classification:** **ACCEPTED**  
**Reviewed repair task:** `t_1d31084f`  
**Independent review task:** `t_105bab0b`

The exact fourth-remediation candidate is **ACCEPTED** for the bounded Slice 2 evaluator remediation only. The current evaluator rejects every supplied development block whose full `[feature_close, label_exit_open]` interval reaches or crosses `selection_from`, and every supplied selection block whose interval reaches or crosses `final_from`. The constraints execute in the integrity CLI and in `evaluate_phase_outcomes`; the unrelated selection-authority gate was replaced only in memory with a synthetic review anchor when necessary to reach the selection structural check, and the crossing exception occurred before any selection outcome was produced.

The accepted five-session clock remains T feature close, T+1 entry open, and T+5 exit open. Required predecessors, ordered boundaries, immutable availability freeze, source availability, pre-receipt rehash, deterministic receipt binding, fail-closed phase authority, exact V5 provenance identity, and protected-adapter immutability all passed fresh independent checks.

No selection or final outcomes were computed. Synthetic writes were confined to Windows temporary directories outside the repository and were removed. This acceptance does not admit data, approve a contract or phase, authorize selection/final evaluation, promote a model, authorize deployment/execution/capital allocation, or change any broker, risk, credential, provider, or schedule state.

## Decisive blockers

**None for the bounded evaluator-remediation acceptance gate.**

### 1. Exact source trace and current repair

Read in full:

- `AGENTS.md`
- `SKILLS/CODE.md`
- `SKILLS/EXAMPLES.md`
- `reports/research/minimum_viable_admission_plan_v1.md`
- `reports/research/spy_momentum_cpu_slice2_review_v1.md`
- `reports/research/spy_momentum_cpu_slice2_remediation_review_v2.md`
- `reports/research/spy_momentum_cpu_slice2_remediation_review_v3.md`
- `reports/research/spy_momentum_cpu_slice2_remediation_review_v4.md`
- `scripts/spy_momentum_cpu_experiment.py`
- `tests/test_spy_momentum_cpu_experiment.py`
- `reports/research/spy_momentum_cpu_slice2_remediation_provenance_v5.json`
- complete Kanban repair receipt for `t_1d31084f`

CodeGraph command:

```text
codegraph explore -p . evaluate_phase_outcomes _contract_availability_freeze _verify_selection_approval _verify_contract_provenance _verify_final_manifest load_spy_rows build_blocks build_partition_blocks assert_partition_isolation assert_partition_purge_and_embargo _verify_receipt_input_hashes main
```

Result: exit `0`; CodeGraph reported 36 symbols across two files and returned the current evaluator call path. Manual source review confirmed that both `main()` and `evaluate_phase_outcomes()` call `build_partition_blocks()` before receipt or outcome creation. At `scripts/spy_momentum_cpu_experiment.py:293-302`, the current code obtains feature and exit session dates and enforces:

- development: feature no later than `development_through` and exit strictly before `selection_from`;
- selection: feature no earlier than `selection_from` and exit strictly before `final_from`;
- final: feature no earlier than `final_from`.

The `.to_numpy()` conversion compares block-ordered arrays and prevents pandas index-label alignment from masking a crossing.

### 2. Prior crossing defect independently reproduced, then rejected by current bytes

The prior crossing shape was rebuilt with the v4 feature-date-only boundary logic recorded in the reviewed source. All predecessor names and ordered boundaries were present; actual label intervals were disjoint from one another, so the legacy overlap/purge checks passed. The legacy gate accepted:

```json
{
  "development": {
    "feature": "2020-01-29",
    "entry": "2020-01-30",
    "exit": "2020-02-05",
    "selection_from": "2020-01-30"
  },
  "selection": {
    "feature": "2020-02-13",
    "entry": "2020-02-14",
    "exit": "2020-02-20",
    "final_from": "2020-02-14"
  },
  "legacy_gate_accepted": true
}
```

Thus the development label entered and exited inside selection, and the selection label entered and exited inside final. Running the same synthetic contract through the exact current final integrity CLI returned non-zero with:

```text
ValueError: development partition date mismatch
```

The V5 manifest's `before` mapping exactly equals the V4 manifest's `after` mapping, preserving the provenance chain from the reviewed v4 candidate to the current v5 candidate.

### 3. Full interval isolation passes both executable paths

External probe command:

```text
PYTHONPYCACHEPREFIX=C:/Users/bgonn/AppData/Local/Temp/v20-risk-slice2-v5-probe-pycache python C:/Users/bgonn/AppData/Local/Temp/v20-risk-slice2-v5-probe.py
```

Decisive result fields:

```json
{
  "development_crossing_both_paths": {
    "cli_rejected": true,
    "cli_error": "ValueError: development partition date mismatch",
    "outcome": {
      "rejected": true,
      "error": "ValueError: development partition date mismatch"
    }
  },
  "selection_crossing_both_paths_pre_outcome": {
    "synthetic_anchor_only": true,
    "cli": {
      "accepted": false,
      "error": "ValueError: selection partition date mismatch",
      "stdout": ""
    },
    "outcome": {
      "rejected": true,
      "error": "ValueError: selection partition date mismatch"
    }
  }
}
```

The synthetic selection anchor changed only the imported module's in-memory constant and matching temporary contract field, solely to pass the unrelated approval check. Both paths stopped at partition validation with empty CLI stdout, before outcome construction. The normal current bytes retained `SELECTION_APPROVAL_ANCHOR_SHA256 = None`.

### 4. Five-session chronology and chronological declaration controls retained

The same independent probe returned:

```json
{
  "five_session_chronology": {
    "cli_accepted": true,
    "feature_positions": [20, 25],
    "entry_positions": [21, 26],
    "exit_positions": [25, 30]
  },
  "predecessor_and_ordered_boundaries": {
    "missing_selection_rejected": true,
    "missing_error": "ValueError: complete chronological partition declaration required",
    "unordered_rejected": true,
    "unordered_error": "ValueError: complete chronological partition declaration required"
  }
}
```

This retains the intended within-session ordering: the first block exits at session 25 open before the next feature is available at session 25 close; the next label begins at session 26 open. Final requires development, selection, and final predecessors, and boundary dates must satisfy `development_through < selection_from < final_from`.

### 5. Availability freeze and source availability retained in both paths

Independent probe results:

```json
{
  "missing_freeze_cli_rejected": true,
  "missing_freeze_outcome_error": "ValueError: contract availability freeze required",
  "post_freeze_source_cli_rejected": true,
  "post_freeze_source_outcome_error": "ValueError: source availability required",
  "pre_session_source_cli_rejected": true,
  "pre_session_source_outcome_error": "ValueError: source availability required"
}
```

The current loader also retains read-only SQLite URI access, required total-return/one-day metadata, unique monotonic timestamps, finite positive OHLC, complete non-empty source mapping, parseable availability dates, and source dates no earlier than their market sessions and no later than the immutable contract freeze.

### 6. Authority remains fail closed

The external probe replaced `load_spy_rows()` with a marker while leaving the exact current selection anchor absent. Result:

```json
{
  "anchor_constant": null,
  "cli_rejected": true,
  "loader_reached": false,
  "outcome_error": "ValueError: selection approval anchor required"
}
```

Final outcome evaluation also retains the unconditional `ValueError: external final approval required for outcome evaluation` after sealed-manifest validation and before data loading. These controls provide denial, not approval; no Product/Brennan phase authority is inferred.

### 7. Pre-receipt rehash and deterministic receipt binding retained

Temporary post-validation mutations produced no receipt stdout and failed as follows:

```json
{
  "contract": "ValueError: contract changed before receipt",
  "database": "ValueError: database changed before receipt",
  "sealed_manifest": "ValueError: sealed manifest changed before receipt"
}
```

Two unchanged integrity runs both returned `0` with byte-identical stdout. The emitted `output_sha256` recomputed exactly over the canonical payload, and the contract, database, and evaluator bindings matched the exact bytes.

The first probe attempt encountered a Windows temporary-file cleanup `PermissionError` on a synthetic SQLite file after all checks. That harness run exited `1` and supplied no evidence. The probe was rerun with deferred cleanup after process exit; the corrected run exited `0`, and shell verification reported:

```text
PROBE_CLEANUP_ABSENT=true
REHASH_PROBE_CLEANUP_ABSENT=true
TEMP_ROOTS_REMAIN=false
```

### 8. Fresh focused tests and external compile

Focused command:

```text
tmp='C:/Users/bgonn/AppData/Local/Temp/v20-risk-slice2-v5-focused'; rm -rf "$tmp"; mkdir -p "$tmp"; python -m pytest tests/test_spy_momentum_cpu_experiment.py -q --basetemp="$tmp/pytest"; rc=$?; printf 'FOCUSED_EXIT=%s\n' "$rc"; rm -rf "$tmp"; if [ ! -e "$tmp" ]; then printf 'FOCUSED_CLEANUP_ABSENT=true\n'; else printf 'FOCUSED_CLEANUP_ABSENT=false\n'; fi; exit "$rc"
```

Result:

```text
...........................................                              [100%]
43 passed in 10.63s
FOCUSED_EXIT=0
FOCUSED_CLEANUP_ABSENT=true
```

External compile command:

```text
tmp='C:/Users/bgonn/AppData/Local/Temp/v20-risk-slice2-v5-compile'; rm -rf "$tmp"; mkdir -p "$tmp"; PYTHONPYCACHEPREFIX="$tmp/pycache" python -m py_compile scripts/spy_momentum_cpu_experiment.py tests/test_spy_momentum_cpu_experiment.py; rc=$?; printf 'PYCOMPILE_EXIT=%s\n' "$rc"; rm -rf "$tmp"; if [ ! -e "$tmp" ]; then printf 'PYCOMPILE_CLEANUP_ABSENT=true\n'; else printf 'PYCOMPILE_CLEANUP_ABSENT=false\n'; fi; exit "$rc"
```

Result:

```text
PYCOMPILE_EXIT=0
PYCOMPILE_CLEANUP_ABSENT=true
```

`git diff --check` returned `DIFF_CHECK_EXIT=0`. The existing `.gitignore` line-ending warning was unrelated to the reviewed evaluator/test/provenance candidate.

### 9. Exact V5 hashes and protected-adapter immutability

Fresh SHA-256 results:

```text
scripts/spy_momentum_cpu_experiment.py bc9b88293021447c527ae3256b9723ec14ff2707c384f155603ab08e88b5e4c8
tests/test_spy_momentum_cpu_experiment.py f7ab005b60bd52ce944fa00dfbebba44d61e544a1652bf284534b1963eda5191
reports/research/spy_momentum_cpu_slice2_remediation_provenance_v5.json a04013dc22f14de53ddcc92de106a123c802064e917e094aa1e7f056fc6430b0
vesper/data/massive/adapters/total_return_ohlcv_adapter_20260717T153500Z.sqlite 825252f94efb228df37683d58a1199cbc101828bbe7f53079e9d066c28e5a70c
EVALUATOR_AFTER_MATCH True
TEST_AFTER_MATCH True
PROTECTED_MATCH True
V5_BEFORE_MATCHES_V4_AFTER True
```

The protected adapter hash was independently measured before and after the probes and remained `825252f94efb228df37683d58a1199cbc101828bbe7f53079e9d066c28e5a70c`. Targeted `git status` for `vesper/data/massive`, `vesper/data/model_research`, `config`, `models`, `scripts/train_model.py`, and `vesper/engine.py` was empty. No reviewed code, test, provenance, protected adapter, configuration, model, schedule, broker/risk/execution state, credential, or provider was modified by Risk; this report is the only project artifact written by the review.

## Residual risk

1. **Bounded acceptance only.** This verdict validates the exact evaluator/test remediation bytes and their fail-closed structural behavior. Data admission, experiment-contract approval, source authority, selection authority, final authority, model promotion, deployment, execution, capital allocation, and broker/risk/schedule/provider actions remain **not evidenced** and unauthorized.
2. **Selection and final outcomes remain intentionally unavailable.** The selection anchor is `None`, and final outcomes raise an external-approval error. The synthetic anchor used for structural coverage is review instrumentation, not authority and not a proposal to populate the production constant.
3. **Historical v4 bytes are content-addressed but not retained as a separately executable local artifact.** The prior defect was independently reproduced from the reviewed v4 feature-date-only logic and exact crossing shape; the V5-before/V4-after hash chain matches. This does not weaken the fresh execution evidence for the exact current v5 bytes but limits byte-for-byte rerunning of the superseded v4 artifact in this task.
4. **The full project suite was not rerun by Risk.** The repair receipt reports `265 passed, 1 failed` from an unrelated Tk runtime limitation and root-level collection conflicts under untracked tool/profile trees. The exact focused evaluator suite and required external compile passed; broader GUI/tooling health is outside this bounded scientific-remediation acceptance.
5. **Timestamp semantics remain contract-sensitive.** The accepted implementation treats declared partition dates as UTC session identifiers while preserving open-before-close ordering by explicit T/T+1/T+5 positions. Any later contract using intraday timestamps or a different calendar requires a new independent review; this acceptance does not generalize beyond the reviewed daily-session contract.

## Next owner

**Next safe owner: V20 Data (`v20-data-engineer`) on child task `t_8572403b`.** Perform the already-authorized read-only post-repair data and evaluation re-audit. Do not infer `GO` from this green evaluator remediation: independently re-check the frozen adapter, provenance, source availability, adjustment basis, and all remaining data-side admission gates. Brennan remains final authority.