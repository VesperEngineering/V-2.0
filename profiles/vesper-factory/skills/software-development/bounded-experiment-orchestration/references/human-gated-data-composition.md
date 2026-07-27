# Human-gated data composition after a no-winner campaign

Use after a bounded local-LLM development campaign concludes that approved data composition—not capacity or schedule—is the next lever. This phase prepares reviewable data only; it does not admit records, train, evaluate a model, or create/open a promotion benchmark.

## Safe build order

1. **Bind current evidence without reopening quarantine.** Hash the no-winner verdict, final verification, approved manifest, authorized development set, and the consumed-benchmark quarantine receipt. Read only the quarantine receipt identity/status. If the source tree has no Git metadata, bind a deterministic raw-byte manifest of the relevant source/config/test files and later bind the exact executed generator file separately.
2. **Freeze the protocol before candidate writes.** Predeclare candidate count and family balance, development-suite balance, reference corpora allowed only for exclusion checks, overlap thresholds, tokenizer/model identity, sequence limit, authority denials, exact review choices, and terminal verdicts.
3. **Diagnose abstractly from authorized development evidence.** Persist counts, family names, record IDs, schema/term/verdict classes, and design implications. Exclude raw prompts, targets, and model responses from the diagnosis receipt. Common structured-output classes are:
   - schema valid but rubric term omitted;
   - correct key family but wrong decision/verdict;
   - generic risk/fix template reused across distinct mechanisms;
   - temporally inverted fix (for example, fitting on future data).
4. **Author before exclusion checking.** Build candidate concepts from an independent authored concept bank using only the abstract diagnosis. Build the `DEVELOPMENT_ONLY` challenge bank separately. Only after both banks are deterministic should the validator load permitted approved/development/holdout references for rejection-only overlap checks. This ordering prevents inspected references from steering authoring.
5. **Keep candidate and development authority distinct.** Candidates remain `PENDING_HUMAN_REVIEW`; development records remain permanently `DEVELOPMENT_ONLY` and ineligible for promotion claims. Every record should carry closed provenance, `derived_from` lineage, case-concept identity, deterministic rubric, and explicit false training/admission/promotion/deployment/execution authority.
6. **Validate semantics and physical viability.** Require unique IDs, exact composition, closed schemas, provenance closure, prohibited-source exclusion, normalized-prompt/assistant-target/case-concept overlap, material concept similarity, required-term alignment, and prohibited positive authority language. Put every rubric-required term in both the user instruction and complete assistant target. With the exact production tokenizer and sequence length, render prompt-only and full conversations without truncation, then prove the full target token sequence survives unchanged; “at least one supervised token remains” is insufficient.
7. **Publish one exact review set.** Use content-addressed candidate and development filenames, create-once writes, raw hash readback, deterministic second-pass regeneration, and receipts that bind protocol, executed generator source, reference paths/hashes, overlap report, composition, tokenizer report, and authority denials. The review packet should expose per-record provenance/lineage, assistant targets, automated results, and protocol-declared human choices. Automated PASS never changes review status.
8. **Sequence closure before the final receipt.** Run the broad tests/static checks, remove temporary runners and pycache, verify cleanup from outside the removed paths, confirm no training/evaluation/GPU process or campaign lock remains, and close the expected campaign-member inventory *before* writing `final-verification.json`. Emit that receipt last, then read back and hash it. If a receipt named final was written before cleanup or idle-resource checks, preserve it as pre-closure evidence and emit a separately named closure receipt that binds it; do not silently overstate the earlier artifact.
9. **Stop at the boundary.** A ready verdict names the exact candidate path and SHA-256. Any missing source binding, stale test result, interrupted final provenance patch, failed cleanup, or unexecuted regeneration gate yields `NOT_READY`; an earlier dry run cannot substitute for the final packet.

## TDD and interaction-budget discipline

Use vertical slices:

1. RED for deterministic bounded candidate generation → GREEN.
2. RED for independent balanced development generation → GREEN.
3. RED for overlap/authority/tokenization rejection → GREEN.
4. RED for content-addressed receipt/review publication and idempotent regeneration → GREEN.
5. Publish one real end-to-end artifact slice before adding optional receipt enrichments.

Reserve the final third of the interaction budget for actual artifact generation, second-pass regeneration, full tests/static checks, JSON/JSONL parsing, hash readback, and cleanup. Do not spend the terminal budget polishing provenance fields while no review packet exists.

## Review checklist

- Promotion benchmark content remained unopened; only its quarantine receipt was bound.
- Candidate authoring preceded reference-corpus overlap loading.
- Candidate and development concept banks are separate and disjoint.
- Rubric terms appear in prompt and target.
- Exact tokenizer proves complete target preservation.
- Candidate status is pending, never approved.
- Development suite states permanently development-only and cannot support promotion.
- Packet binds exact candidate bytes and executed generator bytes.
- Deterministic regeneration and cleanup were executed, not merely unit-tested.
- Final state is exactly ready-for-review or not-ready; no admission/training follows.
