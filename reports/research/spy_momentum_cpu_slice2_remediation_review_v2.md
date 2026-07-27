# SPY Momentum CPU Slice 2 Remediation Independent Review v2

**Review timestamp:** 2026-07-27T00:48:08Z  
**Classification:** **REJECTED**  
**Reviewed task:** `t_bf3c41f1`  
**Independent review task:** `t_f8ea7ced`

## Classification

The remediation is **REJECTED**. Several positive fail-closed controls are executable and the fresh focused suite passes, but four original blocking classes remain materially unresolved and the remediation provenance manifest does not identify the exact current candidate bytes. This verdict does not authorize selection/final outcome computation, model promotion, deployment, execution, capital allocation, or any broker/risk/schedule/provider action.

No selection or final outcomes were computed during this review. All adversarial probes used synthetic temporary SQLite files outside the repository, and cleanup was verified.

## Decisive blockers

### 1. Selection outcome access has no independently trusted phase-approval anchor

**Evidence:** `scripts/spy_momentum_cpu_experiment.py:149-177` accepts a caller-selected phase, caller-supplied contract path, and caller-supplied hash. `_verified_json()` proves only that the supplied bytes match the supplied digest. `_verify_contract_provenance()` proves internal equality to the supplied database and current evaluator; it does not anchor the contract hash or phase approval to a Brennan/Product-approved immutable value. A self-authored `selection` contract therefore passes all pre-load checks.

The non-outcome probe replaced `load_spy_rows()` with a marker exception after constructing a self-authored, internally consistent selection contract. Result:

```text
PROBE_SELECTION_APPROVAL_ANCHOR
{"marker": "REACHED_SELECTION_DATA_LOAD", "self_authored_contract_reached_data_load": true}
```

This probe stopped before data loading or outcome calculation. It demonstrates that the executable path has no external approval check between caller-controlled contract construction and selection-data access. Final outcome access is safer—`evaluate_phase_outcomes("final", ...)` always raises `external final approval required for outcome evaluation` at line 177—but that does not cure the unresolved selection-phase authorization requirement or establish an approved final-manifest anchor.

**Original blocker status:** unresolved for selection; final outcomes fail closed but no executable externally approved final authorization path is evidenced.

### 2. Partition/purge/embargo enforcement is vacuous when the contract omits boundary context

**Evidence:** `build_partition_blocks()` at `scripts/spy_momentum_cpu_experiment.py:235-240` accepts any non-empty partition dictionary. `assert_partition_purge_and_embargo()` at lines 243-250 checks only intervals supplied by that dictionary. It does not require a selection contract to include development boundary context, require a final contract to include pre-final boundary context, bind formation positions to declared partition dates, or enforce the predeclared five-session formation cadence.

A synthetic selection contract containing only `{"selection": [20]}` passed the real CLI integrity path:

```text
PROBE_VACUOUS_PARTITION_GATE
{"returncode": 0, "single_partition_only": true, "stderr_tail": [], "stdout": "{\n  \"phase\": \"selection\",\n  \"spy_rows\": 32,\n  \"integrity_only\": true\n}"}
```

With one supplied partition there is no boundary pair, so the purge and embargo loop performs zero checks. The positive overlap and boundary-leakage tests prove behavior only when the caller supplies competing intervals; they do not prove that required boundary context cannot be omitted.

**Original blocker status:** unresolved. Actual interval checks run in the CLI and outcome entry point, but required partition-boundary completeness is not fail-closed.

### 3. Availability provenance remains unvalidated and adversarial coverage is incomplete

**Evidence:** `load_spy_rows()` at `scripts/spy_momentum_cpu_experiment.py:107-112` requires `source_as_of_date` to be a non-empty string but does not parse it, validate its temporal relationship to the market row, or bind it to a receipt/freeze time. A synthetic adapter in which every `source_as_of_date` was the malformed value `not-a-date` was accepted:

```text
PROBE_AVAILABILITY_VALIDATION
{"malformed_source_as_of_date_accepted": true, "rows": 32}
```

The test named `test_future_discontinuity_does_not_remove_a_known_label` (`tests/test_spy_momentum_cpu_experiment.py:153-160`) changes an outcome-period close to a large finite value; it does not test missingness or availability timing. The source-map test at lines 330-353 tests null/absent fields, not malformed or future availability timestamps.

Positive evidence retained: the current loader rejects missing, NaN, infinite, zero, and negative OHLC through the numeric coercion and finite/positive gate at lines 103-105; absent source rows fail closed; duplicate source mappings create duplicate joined timestamps and are rejected by the timestamp uniqueness gate; non-monotonic timestamps are rejected.

**Original blocker status:** price validation repaired; missingness/availability coverage and availability enforcement remain unresolved.

### 4. CLI output is deterministic but not bound to the admitted inputs

**Evidence:** `main()` prints only `phase`, `spy_rows`, and `integrity_only` at `scripts/spy_momentum_cpu_experiment.py:295-296`. The output omits the verified contract, database, evaluator, freeze, and sealed-manifest hashes. `test_cli_final_integrity_output_is_deterministically_bound` at `tests/test_spy_momentum_cpu_experiment.py:397-407` proves only same-input stdout equality; it does not prove that different bound inputs produce different receipts.

Two synthetic databases with different bytes and two different contracts both passed verification and emitted byte-identical stdout:

```text
PROBE_OUTPUT_BINDING
{"contract_hashes_differ": true, "database_hashes_differ": true, "returncodes": [0, 0], "stdout": "{\n  \"phase\": \"development\",\n  \"spy_rows\": 32,\n  \"integrity_only\": true\n}", "stdout_identical": true}
```

**Original blocker status:** unresolved. Repeatability is evidenced; complete deterministic output binding is not.

### 5. The remediation provenance manifest is stale relative to the exact current candidate

**Evidence:** `reports/research/spy_momentum_cpu_slice2_remediation_provenance_v2.json:7-9` declares evaluator hash `14d7c6a974729bf18f05d7a1c48a61ccd5d6fc3edd0c43a8b8cee9c8a4f47b99` and test hash `03a40a7da1b8716c1fc85f4f714b436b7937f52732a1f515678a4d7e67783cf0`. Fresh Python `hashlib.sha256` results for the exact current files were:

```text
scripts/spy_momentum_cpu_experiment.py 2d01b7214ae775176132190c72a7dec07544edb8caac6ab84abc189f07b7dd75
tests/test_spy_momentum_cpu_experiment.py f50a1777bc315d3dd1b27bc1b4e0269b3a8682c4d502838b99cbd3e27395749f
reports/research/spy_momentum_cpu_slice2_remediation_provenance_v2.json d9fa91e60420acabc84ba95afd0757f3bd2af375c6fa1176af22735e915c8c02
vesper/data/massive/adapters/total_return_ohlcv_adapter_20260717T153500Z.sqlite 825252f94efb228df37683d58a1199cbc101828bbe7f53079e9d066c28e5a70c
```

The mismatch is not explained solely by Windows line endings. LF-normalized current hashes were evaluator `d18b0c543fba9d2d310d66e6b64b01565d4f892a57d04bc20708bf90b468406c` and tests `6373451835ce6c71fe375e53e91682fca348f92a40a304b01d5e36924fc5a33b`, which also do not match the manifest. The developer receipt reports 21 focused tests, while the exact current suite collected and passed 25 parameter-expanded cases.

The protected adapter hash still matches the manifest, but the non-Git before/after receipt does not bind the exact evaluator/tests reviewed here.

**Original acceptance evidence status:** invalid for the current candidate.

## Positive evidence and exact commands/results

### Governing/source review

Read in full:

- `AGENTS.md`
- `SKILLS/CODE.md`
- `SKILLS/EXAMPLES.md`
- `reports/research/minimum_viable_admission_plan_v1.md`
- `reports/research/spy_momentum_cpu_slice2_review_v1.md`
- `scripts/spy_momentum_cpu_experiment.py`
- `tests/test_spy_momentum_cpu_experiment.py`
- `reports/research/spy_momentum_cpu_slice2_remediation_provenance_v2.json`
- full Kanban receipt for `t_bf3c41f1`

CodeGraph command:

```text
codegraph explore -p . evaluate_phase_outcomes _verify_contract_provenance _verify_final_manifest load_spy_rows assert_partition_purge_and_embargo main
```

Result: index reported up to date and returned the current executable path and callers. Manual source review then traced the exact candidate rather than relying on the receipt summary.

### Fresh focused suite

Initial command used an MSYS `/tmp` basetemp whose parent was not visible to native Windows Python:

```text
python -m pytest tests/test_spy_momentum_cpu_experiment.py -q --basetemp=/tmp/v20-risk-slice2-focused-1623/pytest
```

Result: `2 passed, 23 errors`; every error was the same `FileNotFoundError` creating `C:\tmp\...\pytest`. This was a harness-path failure, not a candidate test failure.

Corrected command with a native external basetemp:

```text
python -m pytest tests/test_spy_momentum_cpu_experiment.py -q --basetemp=C:/Users/bgonn/AppData/Local/Temp/v20-risk-slice2-focused-<pid>/pytest
```

Result:

```text
.........................                                                [100%]
25 passed in 4.50s
```

The external temporary directory was removed after execution.

### External compile

```text
PYTHONPYCACHEPREFIX=C:/Users/bgonn/AppData/Local/Temp/v20-risk-slice2-compile-<pid>/pycache python -m py_compile scripts/spy_momentum_cpu_experiment.py tests/test_spy_momentum_cpu_experiment.py
```

Result: exit code `0`, no stderr/stdout. External pycache was removed.

### Hash verification

```text
python -c "from pathlib import Path; import hashlib; paths=['scripts/spy_momentum_cpu_experiment.py','tests/test_spy_momentum_cpu_experiment.py','reports/research/spy_momentum_cpu_slice2_remediation_provenance_v2.json','vesper/data/massive/adapters/total_return_ohlcv_adapter_20260717T153500Z.sqlite']; [print(f'{p} {hashlib.sha256(Path(p).read_bytes()).hexdigest()}') for p in paths]"
```

Result: exact hashes are recorded in blocker 5. The adapter remained `825252f94efb228df37683d58a1199cbc101828bbe7f53079e9d066c28e5a70c`.

### Non-outcome adversarial probes

Command form:

```text
python - <<'PY'
# Loaded the current test helpers with runpy; created only synthetic adapters/contracts
# under C:/Users/bgonn/AppData/Local/Temp; ran the real CLI for integrity-only checks;
# monkeypatched load_spy_rows to stop the selection probe before data access/outcomes;
# directly loaded a synthetic adapter with malformed source_as_of_date; printed JSON evidence.
PY
```

Exact result:

```text
PROBE_OUTPUT_BINDING
{"contract_hashes_differ": true, "database_hashes_differ": true, "returncodes": [0, 0], "stdout": "{\n  \"phase\": \"development\",\n  \"spy_rows\": 32,\n  \"integrity_only\": true\n}", "stdout_identical": true}
PROBE_VACUOUS_PARTITION_GATE
{"returncode": 0, "single_partition_only": true, "stderr_tail": [], "stdout": "{\n  \"phase\": \"selection\",\n  \"spy_rows\": 32,\n  \"integrity_only\": true\n}"}
PROBE_SELECTION_APPROVAL_ANCHOR
{"marker": "REACHED_SELECTION_DATA_LOAD", "self_authored_contract_reached_data_load": true}
PROBE_AVAILABILITY_VALIDATION
{"malformed_source_as_of_date_accepted": true, "rows": 32}
PROBE_CLEANUP python_rc=0 rm_rc=0 absent_rc=0
```

No protected path, project code/data/config/model, schedule, broker/risk/execution state, credential, or provider was modified by these probes.

## Residual risk

1. A caller can create and hash a new selection contract that is internally consistent but not independently approved, then reach the selection evaluation path.
2. Purge/embargo checks can be bypassed by omitting prior-partition boundary context; arbitrary formation positions are not bound to declared partition dates or cadence.
3. Malformed or future availability metadata can be admitted, leaving information-timestamp leakage unclosed.
4. Integrity output can be replayed across materially different contracts/databases with the same phase and row count because it contains no content-addressed bindings.
5. The current evaluator/test bytes are not covered by the task's remediation provenance manifest. Implementation success and a green focused suite therefore cannot substitute for evidence identity.
6. The full project suite was not independently rerun in this task. The remediation receipt reports two unrelated Tk/Tcl environment failures; that claim was not needed to establish the decisive rejection above and remains independently unverified here.

## Next owner

**Next safe owner: V20 Development (`v20-development`).** Repair recommendations only:

- require a Product/Brennan-approved immutable contract/phase authority anchor before selection data access or outcome evaluation;
- require complete chronological partition boundary declarations and enforce dates, cadence, purge, and embargo against those declarations in both CLI and outcome paths;
- parse and validate source availability/receipt timestamps against feature/freeze timing and add true missingness/availability adversarial tests;
- emit a deterministic integrity receipt containing contract, database, evaluator, freeze, sealed-manifest, and output hashes, with tests proving input changes alter the binding;
- regenerate a non-Git before/after provenance manifest for the exact final candidate bytes and reroute a fresh independent Risk Review.

The dependent post-repair data re-audit must remain blocked pending a new independent acceptance verdict.