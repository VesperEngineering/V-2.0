# Proposal Evidence Binding Design

- Status: Approved design
- Date: 2026-08-03
- Owner: V20 operator

## Problem

The controller supplies an evidence-ID allowlist to Qwen's output schema. The
top-level output requires at least one evidence ID, but nested
`AgentProposal.evidence_ids` defaults to an empty tuple. Schema compaction adds
the allowlist enum without adding a lower bound, so Qwen may emit an empty list.
The runtime subset check accepts an empty set, then `ProposalRouter` correctly
denies the proposal for missing evidence.

The 2026-08-03 isolated run confirmed this exact split: all five final analyses
cited `synthetic-evidence`; all eight emitted proposals had empty evidence and
all eight were denied.

## Decision

Change only the controller-generated Qwen schema. Whenever an `evidence_ids`
array is bound to non-empty controller evidence, require the property, preserve
any existing lower bound, and enforce `minItems >= 1`. Keep the existing item
enum.

This affects both top-level and nested evidence arrays. The top-level contract
already has `minItems: 1`, so its behavior is unchanged. Nested proposals gain
the missing requirement. The surrounding `proposals` array remains optional, so
zero proposals is valid.

Do not change the global Pydantic `AgentProposal` contract. Its empty default and
the router denial remain defense in depth for manual, legacy, or otherwise
untrusted proposal producers. Do not copy top-level evidence into a proposal and
do not retry Qwen automatically; evidence attribution must be model-selected
from controller-supplied IDs.

## Data flow

1. Controller supplies immutable evidence keyed by ID.
2. `_response_format` binds every generated `evidence_ids` item to those IDs and
   requires one ID per emitted proposal.
3. Qwen may emit no proposal, or proposals with controller-bound citations.
4. Runtime still rejects any unbound ID.
5. Router admits safe evidence-backed proposals to the controller-owned target,
   requires approval for protected capabilities, and denies missing evidence.
6. Routing remains advisory; no proposal executes itself.

## Files

- `vesper/platform/agent_runner.py`: require nested evidence and add its lower
  bound inside the existing evidence-binding branch.
- `tests/platform/test_quant_agents.py`: prove proposal evidence is required and
  zero proposals remains allowed.
- No contract, router, model, profile, queue, journal, gate, or scheduler changes.

## Verification

Use TDD: add the regression assertions and observe all five role cases fail for
the missing `minItems`; then add the minimum schema line and observe them pass.
Run focused authority/review tests, the full repository suite, static checks, and
an independent authority review.

Finally, use fresh isolated state with exact `qwen:64k`, 65,536 context, one
serialized no-tool turn, and synthetic evidence. Require one safe proposal. The
controller must route it to the expected role without executing it, journals must
verify, and the newly rendered digest must remain unacknowledged.
