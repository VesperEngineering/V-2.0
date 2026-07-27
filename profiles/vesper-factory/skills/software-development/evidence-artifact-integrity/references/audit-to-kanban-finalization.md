# Audit-to-Kanban Finalization

Use when a governed milestone needs an immutable acceptance receipt, a final independent audit, board attachment/closure, and a final milestone receipt.

## Append-only sequence

1. **Write the canonical acceptance receipt once.** Bind exact source/merge/tree, test-log hashes, preservation manifests, authority denials, and `board_closure_pending=true`. Hash the physical receipt file.
2. **Audit that exact hash read-only.** The independent auditor verifies every material field against physical evidence and authorizes only attachment/closure. Any receipt edit invalidates the verdict.
3. **Attach before closing.** Add the acceptance receipt path, physical SHA-256, independent audit ID/verdict, and exact canonical SHA to the correction/acceptance card. Re-read the card to prove the attachment persisted.
4. **Close exactly once.** Complete only the designated correction/acceptance card. Preserve historical completed goals and superseded receipts; do not rewrite their state.
5. **Issue a separate final milestone receipt.** Bind the immutable acceptance receipt hash, final-audit result hash, board task ID, closure event/run identity, final canonical HEAD/tree, and retained authority denials. This receipt is new evidence, not an edit of the audited acceptance receipt.
6. **Final readback.** Verify board closure, final receipt hash, canonical identity, protected-content manifest, no temporary proof schedule, and all required disabled controls.

## Why two receipts

The acceptance receipt exists before board closure so an independent auditor has a stable object to review. Board closure necessarily happens afterward. Editing the audited receipt to flip `closure_pending` would silently invalidate its audit binding. A second final receipt preserves both facts append-only.

## Failure rules

- Audit `HOLD`: do not attach as approval or close the card.
- Attachment failure or ambiguous board readback: keep the card open.
- Card was already closed without the evidence binding: create a linked correction record; never rewrite history.
- Canonical/evidence drift after audit: supersede the audit and rerun against the new exact identities.
- No receipt, audit, comment, or board status grants broker/order, deployment, provider, credential, promotion, capital/risk, scheduler, or remote-push authority.
