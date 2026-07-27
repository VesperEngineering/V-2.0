# Trusted Delivery Shadow Handoff

Use this pattern when a durable task board controls agents while a repository-owned coordinator controls technical evidence and authorization boundaries.

## Boundary

- The coordinator is the only source for Git observations, gate outcomes, evidence roots, review/attestation state, and immutable bindings.
- The board remains a transport/control plane. A bridge must **not** treat a card status, summary, or comment as technical proof.
- A shadow handoff is read-only. It loads coordinator status and prints/emits a packet; it must not import the board client, dispatch workers, write evidence, run gates, record approvals, or execute protected actions.

## Packet minimums

Bind every packet to workflow ID, task ID, candidate SHA, tree SHA, canonical diff digest, evidence-root path, coordinator state, and the next eligible role. Emit every protected authority as explicitly false. Reject malformed identifiers, unknown states, malformed bindings, or any incoming status that claims protected authority.

## Review receipt discipline

A board task marked complete is not automatically a valid review receipt. Compare its retained log to the exact required command list and evidence scope. Treat any of these as **no verdict**:

- provider/API stream errors or missing command-level output;
- a partial test slice when the card required a combined suite;
- checkout-local test artifacts when an external temp root was required;
- review of a different SHA/diff than the frozen candidate.

Preserve the failed/insufficient receipt, clean only the known review-created scratch artifact, keep the candidate frozen, and obtain a fresh independent review with retained command results. Do not convert a technical or operator acknowledgement into a PASS.

## Final transition

After a valid independent review, re-run coordinator status and generate the shadow packet. It should route technical evidence to the reviewer, reviewed evidence to the human approver, and a valid non-executing attestation to `next_role: none`. `approved_not_shipped` remains a terminal evidence state, never a merge or execution authorization.
