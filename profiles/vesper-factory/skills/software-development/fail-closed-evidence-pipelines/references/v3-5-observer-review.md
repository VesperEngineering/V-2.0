# Report-only observer review checklist

## Authority

- No imports or runtime reachability to worker dispatch, provider transport, Kanban mutation, scheduler, broker/order, promotion, risk, deployment, or secret modules.
- Do not trust a legacy daemon’s label: inspect for lease ownership, task selection, runtime invocation, or transport calls.

## Evidence and ledger

- Bind each accepted event to the SHA-256 of the exact allowlisted completed source artifact.
- Reject caller-supplied binding/provenance, future timestamps, schema drift, and source/path mismatch.
- Ledger replay validates ordered timestamps, previous-hash continuity, entry digest, size/row bounds, and strict key sets.
- The resident writer appends and fsyncs; it does not compact or rewrite accepted history.

## Freshness and publication

- Fresh requires both `state=FRESH` and `freshness=FRESH`, a parseable nonfuture timestamp, and age within budget.
- Reconcile newest evidence by source/identity so stale historical rows do not permanently poison recovery.
- If the required status receipt cannot be published, return explicit `UNAVAILABLE`; do not retain a fresh call result.

## Dashboard

- Consume strict bounded status only through a read-only snapshot field and a separately named System/History domain.
- Missing/malformed/tampered state must render unavailable/stale and never create a control or permission inference.

## Test sequencing note

After adding an upstream validation rule, revalidate test fixtures for all downstream error-path tests. A downstream write-failure test must use a source-valid, hash-bound receipt so its result proves the write failure rather than the earlier validation rejection.
