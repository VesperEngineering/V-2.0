# Immutable Correction Receipts (Evidence Chain Repair)

When a fail-closed execution produces a receipt with a contradictory or incorrect metadata field, **do not modify the original receipt, rerun the producer, or retry the execution**. Use the immutable correction receipt pattern.

## Trigger

A frozen, independently reviewed execution receipt has a contradictory field:
- `execution.timed_out=false` + `0.109s` + pre‑provider import failure vs `validation.factor_timeout=true`
- Any metadata field that misclassifies the failure mode and could misroute remediation

## Pattern

1. **Preserve all originals.** Do not overwrite, delete, or edit the frozen receipts. They are immutable evidence of what was recorded at the time.

2. **Produce a new correction receipt pair** (JSON + validation sidecar) that:
   - Names and SHA‑256‑binds every original receipt it supersedes
   - Records the exact contradiction (field, expected value, original value, supporting evidence)
   - Declares the corrected classification (e.g. `NON_TIMEOUT_PRE_PROVIDER_RUNTIME_FAILURE`)
   - Supersedes **only** the incorrect field — all other original fields remain authoritative
   - Preserves the original fail-closed outcome, no‑retry, no‑basket, no‑provider, no‑write status
   - Is itself an ignored generated artifact (not tracked in git)

3. **Validate the correction pair:**
   - JSON validity and schema
   - All SHA‑256 bindings match the originals
   - Supersession is limited to exactly one field
   - Corrected classification is supported by the execution record

4. **Obtain fresh independent review.** The correction receipt is new evidence and needs its own Riley review.

## Why Not Modify the Original

- The original receipt is frozen evidence of what was recorded at the time
- The producer code that emitted the contradictory field may not be in the isolated workspace, or may be a one‑off script that is not tracked in git
- Modifying the original would destroy the audit trail
- The original fail‑closed outcome is correct — only the metadata field is wrong

## Example

From VQ‑20260717‑014 (correction for VQ‑012):

```
Original validation:  factor_timeout=true
Execution evidence:   timed_out=false, elapsed_seconds=0.109, returncode=1,
                      ZoneInfoNotFoundError (tzdata missing) before provider work
Correction:           factor_timeout → false
Corrected class:      NON_TIMEOUT_PRE_PROVIDER_RUNTIME_FAILURE
Supersession:         /checks/factor_timeout only (true→false)
Preserved:            FAIL_CLOSED, no‑retry, no‑basket, no‑provider,
                      no‑write, all denied boundaries
```

## Pitfalls

- Do not issue a correction that changes the execution outcome (PASS → FAIL or vice versa). Corrections are for metadata fields that don't affect the safety verdict.
- Do not use a correction to authorize a retry that was denied by the original scope. A corrected receipt is evidence only; a fresh execution needs fresh explicit authority.
- Do not skip Riley review on the correction. It is new evidence and must be independently reviewed before being relied upon.
- The correction receipt must bind the exact SHA‑256 of the original. If the original has been lost or modified, the correction is not valid.