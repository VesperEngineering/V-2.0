# Batched Human Review and Atomic Candidate Admission

Use this pattern when a large candidate corpus requires explicit human decisions before it may enter training, evaluation, deployment, or another governed manifest.

## Core invariant

A structural validator may recommend a candidate for review, but it must never grant approval. Human review, candidate-file mutation, manifest admission, training authorization, promotion authorization, and execution authorization are separate state transitions.

## Freeze and partition before review

1. Freeze and hash the complete candidate corpus, approved source corpus, and holdout corpus.
2. Partition candidates by immutable provenance before creating packets:
   - eligible candidates derive only from admitted training sources;
   - holdout-derived candidates are excluded from review-for-admission and remain ineligible;
   - missing or ambiguous source identities fail closed.
3. Group repetitive variants by source record so the human reviews the semantic source/target once while still seeing every candidate ID and prompt delta.
4. Embed complete source and candidate records in each packet. Summaries alone are insufficient evidence.

## Packet contract

Each immutable packet should contain:

- exact source and candidate records;
- source/candidate/holdout hashes;
- candidate IDs and source-group cardinality;
- the exact prompt delta or appended context;
- per-candidate checks for pending status, approved source, provenance, unchanged target, expected prompt relation, and holdout exclusion;
- explicit false authority flags for approval, promotion, training, and execution;
- `HUMAN_DECISION_REQUIRED` status even when every automated check passes.

Write all packet JSON, human-readable companions, and checksums into a private staging generation. Publish the generation only after every file is complete, then independently hash and replay all packets. Reopening an existing generation is allowed only when every bound file still verifies.

## Semantic alignment is an admission gate

Structural validity and source-target equality are not semantic review. If a candidate appends or alters an instruction, copying the approved source answer unchanged can create a contradictory prompt/target pair.

Before presenting packets for human approval:

1. Parse the prompt delta into explicit obligations (for example universe, information timestamp, falsifier, missing-data policy, or research-only scope).
2. Require the assistant target to represent every new obligation in an explicit, task-appropriate field or value.
3. Preserve every approved source field; permit only declared target additions and documented normalization such as trimming inherited whitespace.
4. Run the same semantic-alignment predicate inside the candidate reviewer, not only in a one-off packet builder.
5. Count alignment by batch, task type, and variant. A structurally valid but misaligned candidate remains `REJECT`/`HOLD`, never `READY_FOR_HUMAN_APPROVAL`.

If the defect is discovered after human approvals were recorded, stop before application. Preserve the original packets and decisions, write a semantic-hold receipt, regenerate to new IDs/content-addressed paths, and require fresh review. The replacement decision must explicitly supersede the prior receipts and state why; never reinterpret an old approval as approval of repaired bytes.

## Decision receipts without source drift

Record each human batch decision in a separate immutable receipt bound to:

- the exact packet hash;
- the complete ordered candidate-ID set;
- the explicit decision (`APPROVE`, `REJECT`, or individual decisions);
- the human attestation text and timestamp;
- false promotion, training, and execution authority.

Make decision recording idempotent: exact replay returns the existing receipt, while a conflicting decision for the same batch fails closed.

**Do not rewrite the master candidate file after every batch.** Per-batch mutation changes the corpus hash and invalidates all remaining packets. Stage immutable decisions while the frozen review generation remains unchanged. After every required batch has a durable decision, reconcile the complete decision set and perform one atomic candidate-file transition.

## Atomic admission after review closes

Before applying decisions:

1. Verify every packet and decision receipt again.
2. Require complete batch coverage and exactly one decision per candidate.
3. Require the current candidate corpus to match the frozen input hash and embedded records.
4. Reject duplicate IDs, unknown IDs, missing decisions, holdout-derived approvals, and conflicting receipts.
5. Apply decisions in memory, validate the complete output, and atomically replace the candidate corpus once.
6. Emit an admission receipt binding before/after corpus hashes, all decision-receipt hashes, approved/rejected counts, excluded holdout IDs, and explicit authority non-claims.
7. Build and freeze a new training manifest only from records whose durable status is explicitly approved. A promotion helper must never relabel pending records as approved.
8. Run a dry-run admission probe proving that pending candidates promote zero records.

## Freeze the admitted manifest, then seal a genuinely untouched benchmark

After the atomic decision application:

1. Build the admitted manifest only from already-approved source records plus the atomically approved candidate output.
2. Prove unique IDs, explicit approved status, and zero provenance from the frozen development holdout.
3. Publish the manifest to a content-addressed path and emit a receipt binding the decision application, source manifest, approved-candidate artifact, holdout, record counts, and raw manifest SHA-256.
4. Keep training, promotion, and execution authority false unless separately granted. Human content approval and manifest freezing do not authorize a run.

Construct the next promotion benchmark only after the admitted manifest is frozen. To call it untouched:

- author new cases that have not influenced training, candidate selection, or prior model-development decisions;
- prove zero ID, normalized-prompt, assistant-target, and case-concept overlap against the admitted manifest, development holdout, and every prior benchmark;
- require every expected target to pass its own declared rubric, so malformed gold data cannot create a false model failure;
- balance and record task-type counts, mark every record `training_eligible=false`, and bind the frozen manifest hash into the seal receipt;
- state `evaluated_by_base=false` and `evaluated_by_adapter=false`, then independently search evaluation receipts for the benchmark path/hash;
- open the sealed benchmark exactly once only after the model/training inputs are frozen. Any tuning or candidate selection informed by its results invalidates its untouched status for a later promotion claim.

A completed training wrapper, lower loss, development-holdout pass, or sealed benchmark is not a promotion. Promotion requires a durable evaluation receipt against the sealed bytes and a separate explicit decision.

## Pitfalls

- Treating `READY_FOR_HUMAN_APPROVAL` as approval.
- Automatically changing `PENDING_HUMAN_REVIEW` to `APPROVED` inside a promotion function.
- Reviewing holdout-derived variants and relying on a later filter to repair leakage.
- Mutating the source corpus between packets, making later packet hashes stale.
- Recording a batch-level decision without binding every candidate ID.
- Inferring training or promotion authority from a human content-approval decision.
- Overwriting historical invalid evidence instead of preserving it with an explicit inadmissibility/supersession receipt.
