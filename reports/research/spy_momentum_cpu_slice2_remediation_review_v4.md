# SPY Momentum CPU Slice 2 Third Remediation Independent Review v4

**Review timestamp:** 2026-07-27T01:27:52Z  
**Classification:** **REJECTED**  
**Reviewed repair task:** `t_c31560a5`  
**Independent review task:** `t_15b8a3ce`

## Classification

The exact third-remediation candidate is **REJECTED**. The current bytes close the previously reported missing-predecessor, unordered-boundary, five-session cadence, mandatory availability-freeze, source-availability, pre-receipt rehash, deterministic receipt, and provenance-identity defects in the exercised paths. They do not close the governing partition-boundary leakage rule: the real final integrity CLI accepts development and selection labels whose entry/exit intervals cross the declared `selection_from` and `final_from` boundaries.

No selection or final outcomes were computed. Outcome-path probes were limited to synthetic development data or fail-before-load/fail-before-outcome cases. Final-phase probes invoked only the integrity CLI. All synthetic databases, contracts, manifests, and the probe script were outside the repository under `C:/Users/bgonn/AppData/Local/Temp` and were removed. This verdict validates no data, supplies no selection/final authority, promotes no model, authorizes no deployment or execution, and changes no broker, risk, capital, provider, credential, or schedule state.

Fresh positive evidence for the exact candidate:

- Final requires exactly `development`, `selection`, and `final`; a missing selection predecessor was rejected with `ValueError: complete chronological partition declaration required`.
- Declared boundaries must satisfy `development_through < selection_from < final_from`; an equal/unordered selection/final boundary was rejected with the same fail-closed error.
- Synthetic development formations `[20, 25]` passed both CLI and outcome paths. They produced feature positions `[20, 25]`, entries `[21, 26]`, and exits `[25, 30]`. The first exit occurs at session 25 open, before the second signal becomes available at session 25 close; the executable label intervals `[21-open, 25-open]` and `[26-open, 30-open]` do not overlap.
- Removing `freeze.availability_freeze` was rejected in CLI and outcome paths with `ValueError: contract availability freeze required`; there is no wall-clock fallback in the reviewed code.
- Synthetic `source_as_of_date` values before their market session and after the immutable freeze were rejected in both CLI and outcome paths with `ValueError: source availability required`.
- Synthetic concurrent mutation of contract, database, and final manifest after structural validation but before receipt emission was rejected respectively with `contract changed before receipt`, `database changed before receipt`, and `sealed manifest changed before receipt`; no stdout receipt was emitted.
- Two identical integrity runs returned zero with byte-identical stdout. The emitted `output_sha256` recomputed exactly over the canonical payload, and the contract/database bindings matched their bytes.
- Selection remains fail-closed before data access because `SELECTION_APPROVAL_ANCHOR_SHA256` is `None`; the marker loader was not reached.
- V4 provenance exactly matches evaluator and test bytes. The protected adapter remained byte-identical before and after the review.

## Decisive blockers

### 1. Label intervals can cross declared chronological partition boundaries

The governing plan requires that no label interval cross a partition boundary and that every formation whose `[feature_time, label_exit_time]` intersects another partition be excluded (`reports/research/minimum_viable_admission_plan_v1.md:67-76`).

The current evaluator does not enforce that rule against declared dates:

- `build_blocks()` sets feature T, entry T+1 open, and exit T+5 open (`scripts/spy_momentum_cpu_experiment.py:148-168`).
- `build_partition_blocks()` checks only each block's **feature date** against `development_through`, `selection_from`, and `final_from` (`scripts/spy_momentum_cpu_experiment.py:289-299`). It never checks entry or exit timestamps against those boundaries.
- `assert_partition_isolation()` checks overlap only among supplied label intervals (`scripts/spy_momentum_cpu_experiment.py:236-243`).
- `assert_partition_purge_and_embargo()` derives its boundary from the earlier supplied label's maximum exit position, not from the contract's declared date boundary (`scripts/spy_momentum_cpu_experiment.py:303-310`). Consequently, separated supplied labels can pass even though an earlier label lies inside a later declared partition.

A fresh synthetic final contract contained all three required predecessors, strictly ordered declared dates, valid five-session cadence values, a valid immutable freeze, valid source availability, and a correctly bound final manifest. Its actual formations satisfied the evaluator's one-sided feature-date checks:

```text
development feature: 2020-01-29 (position 20)
development entry:   2020-01-30 (position 21)
development exit:    2020-02-05 (position 25)
selection_from:      2020-01-30

selection feature:   2020-02-13 (position 31)
selection entry:     2020-02-14 (position 32)
selection exit:      2020-02-20 (position 36)
final_from:          2020-02-14
```

The development label therefore enters and exits inside the declared selection partition, and the selection label enters and exits inside the declared final partition. The real final integrity CLI nevertheless returned `0` with no stderr:

```json
{
  "accepted": true,
  "returncode": 0,
  "stderr_tail": []
}
```

This is not a vacuous cadence case or an actual-label overlap case. It proves the missing relation between declared chronological boundaries and each block's full information/label interval. A green integrity receipt can therefore attest to a contract that violates the predeclared partition isolation rule. The bounded evaluator remediation remains scientifically invalid until this class fails closed in both CLI and outcome paths.

Exact review commands and results:

```text
codegraph explore -p . evaluate_phase_outcomes _contract_availability_freeze _verify_contract_provenance _verify_final_manifest load_spy_rows build_blocks build_partition_blocks assert_partition_isolation assert_partition_purge_and_embargo _verify_receipt_input_hashes main
```

Result: exit `0`; 36 symbols across two files were returned, including the exact current evaluator callers and bodies used above.

```text
tmp='C:/Users/bgonn/AppData/Local/Temp/v20-risk-slice2-v4-focused'; rm -rf "$tmp"; mkdir -p "$tmp"; python -m pytest tests/test_spy_momentum_cpu_experiment.py -q --basetemp="$tmp/pytest"; rc=$?; printf 'FOCUSED_EXIT=%s\n' "$rc"; rm -rf "$tmp"; if [ ! -e "$tmp" ]; then printf 'FOCUSED_CLEANUP_ABSENT=true\n'; else printf 'FOCUSED_CLEANUP_ABSENT=false\n'; fi; exit "$rc"
```

Result:

```text
........................................                                 [100%]
40 passed in 9.83s
FOCUSED_EXIT=0
FOCUSED_CLEANUP_ABSENT=true
```

```text
tmp='C:/Users/bgonn/AppData/Local/Temp/v20-risk-slice2-v4-compile'; rm -rf "$tmp"; mkdir -p "$tmp"; PYTHONPYCACHEPREFIX="$tmp/pycache" python -m py_compile scripts/spy_momentum_cpu_experiment.py tests/test_spy_momentum_cpu_experiment.py; rc=$?; printf 'PYCOMPILE_EXIT=%s\n' "$rc"; rm -rf "$tmp"; if [ ! -e "$tmp" ]; then printf 'PYCOMPILE_CLEANUP_ABSENT=true\n'; else printf 'PYCOMPILE_CLEANUP_ABSENT=false\n'; fi; exit "$rc"
```

Result:

```text
PYCOMPILE_EXIT=0
PYCOMPILE_CLEANUP_ABSENT=true
```

```text
python -c "from pathlib import Path; import hashlib, json; paths=['scripts/spy_momentum_cpu_experiment.py','tests/test_spy_momentum_cpu_experiment.py','reports/research/spy_momentum_cpu_slice2_remediation_provenance_v4.json','vesper/data/massive/adapters/total_return_ohlcv_adapter_20260717T153500Z.sqlite']; actual={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}; manifest=json.loads(Path(paths[2]).read_text()); print('ACTUAL'); [print(p,actual[p]) for p in paths]; print('EVALUATOR_MATCH',actual[paths[0]]==manifest['after'][paths[0]]); print('TEST_MATCH',actual[paths[1]]==manifest['after'][paths[1]]); print('PROTECTED_MATCH',actual[paths[3]]==manifest['protected_adapter']['sha256_before_and_after'])"
```

Result:

```text
scripts/spy_momentum_cpu_experiment.py e8e72f894da8f601b5199def07fe99c5d0928c8a125b720b478a14c969c5cf0f
tests/test_spy_momentum_cpu_experiment.py 07e2121ee9ac697a522e34935460961d169cb29a9ea5e9803e823aacfd4a3d63
reports/research/spy_momentum_cpu_slice2_remediation_provenance_v4.json 47b69c8f72574c3ea35473f47b85dd982f574c8bcaab64d0cbf6f01f50d645fe
vesper/data/massive/adapters/total_return_ohlcv_adapter_20260717T153500Z.sqlite 825252f94efb228df37683d58a1199cbc101828bbe7f53079e9d066c28e5a70c
EVALUATOR_MATCH True
TEST_MATCH True
PROTECTED_MATCH True
```

The adversarial command was:

```text
python C:/Users/bgonn/AppData/Local/Temp/v20-risk-slice2-v4-probe.py
```

It exited `0`. In addition to the decisive accepted crossing above, it independently returned the positive control results listed under Classification. Shell cleanup then reported:

```text
PROBE_SCRIPT_CLEANUP_ABSENT=true
PROBE_ROOT_CLEANUP_ABSENT=true
PROTECTED_ADAPTER_AFTER 825252f94efb228df37683d58a1199cbc101828bbe7f53079e9d066c28e5a70c
```

## Residual risk

1. The 40-case focused suite has no adversarial case in which feature dates satisfy their one-sided partition checks but label entry/exit timestamps cross `selection_from` or `final_from`. Its boundary tests therefore overstate full chronological isolation.
2. The exact repair independently evidences five-session cadence and non-overlap among supplied labels, but it does not evidence the governing requirement that full `[feature_time, label_exit_time]` intervals remain within their declared chronological partitions.
3. The full project suite was not independently rerun in this Risk review. Development's `262 passed, 1 failed` Tk-runtime account remains a receipt claim; it is not needed for the decisive rejection above.
4. No external selection anchor exists for these evaluator bytes. Selection is deliberately unavailable, and this rejection does not create phase authority.
5. The protected adapter hash and V4 provenance identity are valid only as byte-identity evidence. They do not admit the adapter, reconstruct external raw inputs, authorize selection/final evaluation, or validate any strategy outcome.

## Next owner

**Next safe owner: V20 Development (`v20-development`).** Repair recommendation only:

- enforce each supplied block's complete `[feature_close, label_exit_open]` interval against the exact declared chronological partition boundaries, not just its feature date;
- add non-vacuous CLI and outcome tests where a development label crosses `selection_from` and a selection label crosses `final_from`, and require both to fail closed while retaining the accepted T/T+1/T+5 five-session cadence case;
- regenerate provenance for the exact final evaluator/test bytes and route a fresh independent Risk review.

Risk does not repair or approve its reviewed candidate. Product or Brennan must establish source authority on the exact V20 Kanban card after independently reviewable bytes exist.