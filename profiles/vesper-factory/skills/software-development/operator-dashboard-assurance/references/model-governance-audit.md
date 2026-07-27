# Read-only model-governance audit reference

Use this reference when auditing champion/challenger admission, registry identity, promotion receipts, or operator-control truthfulness without mutating artifacts.

## Evidence sequence

1. Capture repository state before inspection. Preserve dirty worktree state and do not generate receipts or run artifact-writing validators.
2. Enumerate all promotion evaluators and consumers, especially parallel `app/` and `backend/` implementations.
3. Run a pure evaluator probe with an incomplete proposal through every implementation. Record decision semantics and field names.
4. Inspect top-level receipt status separately from nested decision status. A safety boundary of all-false does not make a blocked decision green.
5. Parse registry-declared active path and hash. Independently discover the inferred runtime checkpoint set and hashes. Compare exact `(path, hash)` pairs; global hash membership is insufficient.
6. Inspect current-picks, model-history, prediction, and outcome-ledger schemas for model ID, checkpoint paths/hashes, feature-schema hash, data cutoff, and code SHA.
7. Inspect operator status builders for existence-only or hardcoded health. Probe missing/unknown input and require `blocked`, `unknown`, or `stale`, never `clear`/green by default.
8. Inspect rollback scope. Registry-only backup is insufficient for runtime-affecting changes; require a pre-change manifest covering pointers, checkpoint hashes, schema/config hashes, code SHA, and consumers.
9. Check tracked and untracked generated surfaces for credential markers without printing values. Report verified absence separately from unverified secret stores.

## Safe pure probes

```bash
python - <<'PY'
from pathlib import Path
from app.services import model_promotion_gate as app_gate
from backend.app.services import model_promotion_gate as backend_gate

proposal = {"proposal_id": "audit", "confidence": 0.8, "variance": 0.0}
print("app:", app_gate.evaluate_proposal(proposal))
print("backend:", backend_gate.evaluate_proposed_update(proposal))
PY
```

For registry comparison, call the inventory module's read-only helpers with `write_reports=False` when using its public entrypoint, or call its pure parser/discovery helpers directly. Always record the actual SHA-256 values and the exact mismatch reason.

For operator health, call the status builder with an empty or fixture root in memory only. Verify that missing evidence cannot appear in `healthy_artifacts`, and that unknown execution state cannot produce `fail_closed_state=clear`.

## Reporting template

For each finding record:

- Severity and trust impact.
- Displayed claim or receipt status.
- Exact implementation path and line range.
- Authoritative source and whether it is current, stale, or contradictory.
- Non-mutating reproduction command and observed output.
- Minimal safe repair that preserves all authority gates.
- Whether the evidence came from a pure source probe, focused test, or live runtime check.

Lead with `trustworthy`, `degraded`, or `not yet trustworthy`. State explicitly when broad tests were intentionally not run because they would write artifacts. Note overlapping implementation surfaces rather than assuming one is dead code.
