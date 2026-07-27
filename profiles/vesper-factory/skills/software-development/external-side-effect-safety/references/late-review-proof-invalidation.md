# Late Independent Review and Descendant Proof Invalidation

Use when an independent safety review runs asynchronously while source-bound canaries, receipts, schedules, dashboards, or integration steps are downstream.

## Proof barrier

Model the chain explicitly:

`source candidate -> independent code review -> supervised canary -> independent canary review -> recovery proof -> natural schedule run -> read-only projection -> integration`

Do not launch a descendant proof while the review governing its source or safety boundary is still pending. A local commit may preserve an unchanged reviewed patch, but it does not turn a pending verdict into approval. Never install a natural proof schedule or publish a positive dashboard projection before the governing exact candidate is approved.

## When a late HOLD arrives

1. Compare the review's pinned base, diff/commit hash, and file scope with the current candidate. If it applies, stop treating every descendant artifact as admissible immediately.
2. Preserve original receipts, logs, databases, and scheduler evidence byte-for-byte. Add a separate bounded disposition such as `HELD_SUPERSEDED` with the rejected source, receipt hash, reviewer finding, and hard-false authority fields.
3. Pause/remove any active proof schedule and prevent stale wrappers from being reused. A one-shot run that already completed remains historical evidence, not final proof.
4. Remove or replace positive read-only projections that would display the rejected source as approved. Do not leave dashboard truth ahead of the review record.
5. Restore temporary least-privilege profile/config changes even when the proof is rejected.
6. Reproduce each finding with a failing regression, implement the smallest repair, run focused/broad gates, and obtain a fresh review bound to the successor SHA.
7. Re-run every source-dependent descendant proof. Do not carry forward a worker canary, closure receipt, natural schedule run, or projection produced from the rejected source.

## Evidence language

Say **historical, held, superseded, no authority** for rejected descendants. Do not delete them, call them successful final proof, or imply that a deterministic `ACCEPTED` evaluation overcomes a safety-review HOLD.
