# SPY Momentum CPU Slice 2 Second Remediation Independent Review v3

**Review timestamp:** 2026-07-27T01:07:21Z  
**Classification:** **REJECTED**  
**Reviewed repair task:** `t_bf3c41f1`  
**Independent review task:** `t_0777ca8c`

## Classification

The exact second-remediation candidate is **REJECTED**. Selection authority now fails before database access when no externally approved immutable anchor is compiled into the evaluator; the integrity receipt is content-addressed and changes with admitted contract/database bytes; source availability strings are parsed and checked when an explicit freeze is supplied; and the v3 provenance hashes match the exact evaluator/test bytes. Those positive controls do not cure two decisive fail-closed defects: the executable chronology gate accepts an incomplete and internally contradictory final partition declaration while rejecting the authoritative five-session cadence, and the executable availability path accepts a contract with no immutable availability freeze by falling back to the reviewer's wall clock.

No selection or final outcomes were computed. All executable probes used synthetic SQLite databases and contracts under `C:/Users/bgonn/AppData/Local/Temp`; the probe script and all temporary roots were removed. This verdict does not admit data, supply selection authority, authorize model promotion, deployment, execution, capital allocation, or permit any broker/risk/schedule/provider action.

## Decisive blockers

### 1. Required chronology, boundary dates, predecessors, and cadence are not complete or contract-correct

**Source evidence:** `scripts/spy_momentum_cpu_experiment.py:249-280` sets the required partition names to `{"development", phase}` for every non-development phase. A final contract therefore does not require the selection predecessor. The same function independently checks only that development formations are not later than `development_through` and phase formations are not earlier than `<phase>_from`; it never establishes an ordered boundary relation such as `development_through < selection_from < ... < final_from`. It also requires `formation_cadence_sessions == HOLDING_SESSIONS + 1`, i.e. six sessions, and requires adjacent positions to differ by six.

The governing contract in `reports/research/minimum_viable_admission_plan_v1.md:69-76,81-93` requires the formation schedule to advance in **five-session increments**, requires non-overlapping five-session labels, and places final only after the pre-freeze/selection history plus embargo. The current evaluator instead collapses feature-close and exit-open timing into integer row positions and uses a six-position cadence to avoid an inclusive positional overlap. That is not the exact predeclared information/execution clock.

Fresh synthetic integrity-only probes produced:

```text
"incomplete_final_chronology": {
  "accepted_without_selection_partition": true,
  "declared_boundaries_overlap": true,
  "returncode": 0,
  "stderr_tail": []
}
"predeclared_five_session_cadence": {
  "accepted": false,
  "returncode": 1,
  "stderr_tail": ["ValueError: complete partition declaration required"]
}
```

The accepted final contract contained only `development: [20]` and `final: [31]`, declared `development_through = 2020-12-31`, and declared `final_from = 2020-01-01`. Its sealed manifest was valid and the real CLI returned zero. Thus the current checks can accept a final integrity receipt when the selection partition is absent and the declared final boundary starts before the declared development boundary ends. Conversely, the exact five-session cadence in the governing plan is rejected before the actual cadence check.

**Prior blocker status:** unresolved. Partitions are non-empty and interval/purge/embargo functions execute, but required predecessor completeness, declared boundary ordering, exact date-clock semantics, and the authoritative cadence are not fail-closed.

### 2. Availability is not bounded to an immutable contract freeze when freeze metadata is absent

**Source evidence:** `scripts/spy_momentum_cpu_experiment.py:120-124` parses `source_as_of_date`, compares it with the normalized market-session date, and compares it with `availability_freeze`. However, when `availability_freeze` is absent, line 122 substitutes `pd.Timestamp.now(...)`. Both executable callers at lines 192 and 335 obtain the value from optional `contract.get("input", {}).get("metadata", {}).get("generated_at")`. Neither `_verify_contract_provenance()` nor `build_partition_blocks()` requires that immutable timestamp or binds it to an approved freeze timestamp.

A fresh synthetic development contract with its entire `input` object removed passed the real CLI:

```text
"missing_contract_availability_freeze": {
  "accepted": true,
  "returncode": 0,
  "stderr_tail": []
}
```

This means the same contract can admit or reject source timestamps as wall-clock time advances, and availability is not bounded against a content-addressed experiment freeze. The focused parameterized tests do prove rejection of malformed, pre-session, and future dates, but they call `load_spy_rows()` without an explicit freeze and do not test that the CLI or outcome path rejects a missing immutable freeze.

**Prior blocker status:** partially repaired but still unresolved. Parsing and explicit-bound comparisons are present; required immutable freeze completeness is fail-open.

## Positive evidence retained

### Selection authority ordering — validated for the anchor-absent candidate

`SELECTION_APPROVAL_ANCHOR_SHA256` is `None` at `scripts/spy_momentum_cpu_experiment.py:18`. Both `evaluate_phase_outcomes()` and `main()` invoke `_verify_selection_approval()` before `load_spy_rows()`.

The independent probe used an internally consistent selection contract naming a deliberately nonexistent database and replaced `load_spy_rows()` with a marker. Result:

```text
"selection_without_anchor": {
  "database_exists": false,
  "error": "ValueError: selection approval anchor required",
  "load_spy_rows_reached": false
}
```

This validates only the required fail-closed behavior while the external anchor is absent. It does not create or evidence an approved Product/Brennan selection anchor.

### Deterministic integrity binding — validated for the reviewed path

`scripts/spy_momentum_cpu_experiment.py:338-347` emits bindings for contract, database, evaluator, canonical freeze, and sealed-manifest hashes, then computes `output_sha256` over the canonical receipt payload excluding the hash field itself. `_verify_final_manifest()` at lines 69-80 binds the sealed manifest to the contract, database, evaluator, and freeze hashes.

A probe changed valid contract bytes while holding the database fixed. Both integrity runs returned zero; the bound contract hashes and output hashes changed; and both output hashes recomputed exactly:

```text
"receipt_contract_binding": {
  "bound_contract_hashes_differ": true,
  "contract_hashes_differ": true,
  "output_hash_a_recomputes": true,
  "output_hash_b_recomputes": true,
  "output_hashes_differ": true,
  "returncodes": [0, 0]
}
```

The focused suite also passed `test_cli_receipt_changes_when_bound_database_changes`, and the final CLI tests exercised sealed-manifest binding. This closes the prior replay-equivalent output defect for fixed inputs. It does not cure the incomplete admitted-input schema in blockers 1 and 2.

### Exact current provenance identity — validated

Fresh SHA-256 values were:

```text
scripts/spy_momentum_cpu_experiment.py ae3adda3b8e2253a129d70eebdaf67e30d3b487693039b06c37ccbec8c161c09
tests/test_spy_momentum_cpu_experiment.py a623af3c565a583c5a5dfb8e2117db0c9968f8ce7062d38017bc74bbd913e835
reports/research/spy_momentum_cpu_slice2_remediation_provenance_v3.json 97be82dd9c2f02fe0550d0ba43656ad272f1dd919af9c80d88827c3bf5085fe5
vesper/data/massive/adapters/total_return_ohlcv_adapter_20260717T153500Z.sqlite 825252f94efb228df37683d58a1199cbc101828bbe7f53079e9d066c28e5a70c
```

The evaluator, test, and protected-adapter values exactly match `reports/research/spy_momentum_cpu_slice2_remediation_provenance_v3.json:7-13`.

## Exact commands and results

### Required source and receipt review

Read in full:

- `AGENTS.md`
- `SKILLS/CODE.md`
- `SKILLS/EXAMPLES.md`
- `reports/research/minimum_viable_admission_plan_v1.md`
- `reports/research/spy_momentum_cpu_slice2_review_v1.md`
- `reports/research/spy_momentum_cpu_slice2_remediation_review_v2.md`
- `scripts/spy_momentum_cpu_experiment.py`
- `tests/test_spy_momentum_cpu_experiment.py`
- `reports/research/spy_momentum_cpu_slice2_remediation_provenance_v3.json`
- full Kanban receipts for `t_bf3c41f1` and prior review `t_f8ea7ced`

CodeGraph command:

```text
codegraph explore -p . evaluate_phase_outcomes _verify_selection_approval _verify_contract_provenance _verify_final_manifest load_spy_rows build_partition_blocks assert_partition_purge_and_embargo main
```

Result: exit `0`; CodeGraph found 61 symbols across three files and returned the current executable callers/source. Manual review traced the exact current candidate.

### Fresh focused suite

The first native basetemp command removed the parent but did not recreate it:

```text
tmp='C:/Users/bgonn/AppData/Local/Temp/v20-risk-slice2-v3-focused'; rm -rf "$tmp"; python -m pytest tests/test_spy_momentum_cpu_experiment.py -q --basetemp="$tmp/pytest"
```

Result: `2 passed, 29 errors`; every error was the same Windows `FileNotFoundError` creating the absent basetemp parent. This was a review-harness path failure, not a candidate failure. Cleanup reported `FOCUSED_CLEANUP_ABSENT=true`.

Corrected command:

```text
tmp='C:/Users/bgonn/AppData/Local/Temp/v20-risk-slice2-v3-focused'; rm -rf "$tmp"; mkdir -p "$tmp"; python -m pytest tests/test_spy_momentum_cpu_experiment.py -q --basetemp="$tmp/pytest"; rc=$?; rm -rf "$tmp"; exit $rc
```

Result:

```text
...............................                                          [100%]
31 passed in 6.67s
FOCUSED_EXIT=0
FOCUSED_CLEANUP_ABSENT=true
```

### External compile

```text
tmp='C:/Users/bgonn/AppData/Local/Temp/v20-risk-slice2-v3-compile'; rm -rf "$tmp"; PYTHONPYCACHEPREFIX="$tmp/pycache" python -m py_compile scripts/spy_momentum_cpu_experiment.py tests/test_spy_momentum_cpu_experiment.py; rc=$?; rm -rf "$tmp"; exit $rc
```

Result:

```text
PYCOMPILE_EXIT=0
PYCOMPILE_CLEANUP_ABSENT=true
```

### Current hashes

```text
python -c "from pathlib import Path; import hashlib; paths=['scripts/spy_momentum_cpu_experiment.py','tests/test_spy_momentum_cpu_experiment.py','reports/research/spy_momentum_cpu_slice2_remediation_provenance_v3.json','vesper/data/massive/adapters/total_return_ohlcv_adapter_20260717T153500Z.sqlite']; [print(f'{p} {hashlib.sha256(Path(p).read_bytes()).hexdigest()}') for p in paths]"
```

Result: the four exact values recorded under provenance identity above.

### Non-outcome adversarial probes

A temporary external Python script used the current test fixture builders to create only synthetic adapters/contracts, invoked the real CLI for integrity-only paths, and directly called the outcome entry point only with a nonexistent database plus a pre-load marker to prove authority ordering. Command:

```text
python C:/Users/bgonn/AppData/Local/Temp/v20-risk-slice2-v3-probe.py
```

Exact decisive result fields are quoted in blockers 1 and 2 and the positive-evidence sections. The command exited `0`; shell cleanup reported:

```text
PROBE_SCRIPT_CLEANUP_ABSENT=true
PROBE_ROOTS_REMAINING=0
```

No project code, tests, data, config, model, schedule, broker/risk/execution state, credentials, provider, or protected path was modified by the probes.

## Residual risk

1. The 31-case suite does not cover the accepted incomplete final chronology, contradictory declared date boundaries, authoritative five-session cadence, or missing immutable availability freeze. Green implementation tests therefore overstate the exact contract coverage.
2. The evaluator models information and execution clocks as row positions. It does not represent the within-session ordering between an exit at the session open and a new feature available after the session close, which is material to the five-session schedule and overlap assertion.
3. `main()` verifies inputs before loading and emits their supplied hashes but does not re-hash contract/database/manifest immediately before emitting the receipt. Concurrent mutation during an integrity-only run remains not evidenced as closed; the outcome path has explicit post-evaluation contract/database rechecks.
4. The full project suite was not independently rerun in this review. The Development receipt claims 254 passes; that claim is not needed for this rejection and remains independently not evidenced here.
5. No external selection anchor exists for these evaluator bytes. Selection remains deliberately unavailable; no acceptance or review verdict may be inferred as phase authority.

## Next owner

**Next safe owner: V20 Development (`v20-development`).** Repair recommendations only:

- require the exact chronological predecessor set for each phase, including selection before final; reject overlapping or unordered declared date boundaries; and validate actual formations against exact declared boundary dates rather than loose upper/lower bounds;
- implement the governing five-session formation cadence with explicit feature-close, next-open entry, and exit-open time ordering, then run non-vacuous multi-block cadence and interval tests in both CLI and outcome paths;
- require an immutable contract availability-freeze timestamp, bind it to the approved freeze/contract, and reject missing values instead of substituting wall-clock `now`;
- add adversarial CLI and outcome tests reproducing both decisive probes, then regenerate provenance for the exact final bytes and route a fresh independent Risk review.

Risk does not repair or approve its reviewed candidate. Product or Brennan must establish source authority on the appropriate V20 card after Development returns independently reviewable bytes.