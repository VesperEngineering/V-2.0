# V20 platform-gap knowledge and portability contract v1

**Decision owner:** Brennan  
**Scope:** proposed, platform-neutral design for G3 shared structured project knowledge and G11 portability. This is documentation only. It neither changes Hermes profiles, memory, Kanban, schedules, code, configuration, data, models, providers, broker, risk, execution, nor authority.

## 1. Purpose, evidence boundary, and assumptions

`reports/agent_platform_strategy.md:194-201` identifies G3 as absent and calls for a compact provenance-rich project index pointing to canonical reports, not copied raw context. Lines 272-279 identify G11 as only partial and require platform-neutral task contracts, evidence schemas, role definitions, and acceptance gates where practical. The current role SOUL files establish distinct Data, Quant, ML Systems, Portfolio, Risk, Development, and Product responsibilities, but their runtime storage is Hermes-specific. `reports/platform_gap_lifecycle_contract_v1.md` already proposes platform-neutral workflow, receipt, identity, lease, and evidence semantics for G4/G8.

**Observed evidence [E].** Canonical V20 evidence exists as reports, research receipts, artifact metadata, source hashes, role contracts, and task/run/event records. The research admission review remains `NO-GO` for new broad experiments; a knowledge index must preserve that decision rather than summarize it as readiness. The current platform authority audit finds G1/G9 absent and G2/G12 partial. These are evidence inputs, not authority to alter them.

**Design assumptions / new requirements [N].** A minimal index can be stored in a platform-neutral, V20-controlled file format and read by any adapter. The index is a locator and verification layer, never a second copy of report prose, raw transcripts, protected data, or secret material. A platform adapter may read, search, route, and render entries, but cannot use the index to grant authority, skip lifecycle guards, or replace the canonical artifact.

## 2. Core invariants

1. **Canonical pointer, not context copy [N].** Each entry names a canonical local path or stable URI and its content hash. It may contain a short, bounded claim title and one-line verification state, but no raw report body, prompt transcript, data rows, credentials, or unbounded log text.
2. **Evidence before assertion [N].** A shared fact must cite at least one canonical evidence artifact and its hash. An uncited proposal, inference, or worker narrative is indexed only as `PROPOSAL` or `UNVERIFIED`, never as fact.
3. **Immutable provenance [N].** An entry never overwrites the provenance it supersedes. Corrections, invalidations, and expiry produce a new revision/event that points back to the prior entry.
4. **Fail closed [N].** Missing path, unreadable artifact, hash mismatch, missing scope, expired validity, unresolved contradiction, or secret-classification failure makes the entry `INVALID` or `UNAVAILABLE`; consumers must not treat it as verified.
5. **Scope separation [E/N].** Global preference, project fact, role-local working knowledge, and task execution state are distinct namespaces. Role/task content is not promoted to shared project fact without evidence and an explicit curator decision.
6. **No authority implication [E/N].** A verified artifact proves only the stated evidence. It does not authorize execution, risk changes, data mutation, schedules, paid compute, promotion, deployment, capital, credentials, broker access, or any other denied authority.

## 3. Namespaces and retention

| Scope | Permitted content | Visibility and ownership | Validity / retention | Promotion rule |
|---|---|---|---|---|
| `global` | Redacted user preferences and platform-operational facts unrelated to a V20 scientific claim. | User/platform owner; never a substitute for V20 project evidence. | Must have explicit expiry or review date. | Never automatically copied into `project`. |
| `project` | Curated V20 facts, decisions, role contracts, canonical artifact pointers, and research-state verdicts. | Readable by V20 roles through a platform adapter; Product curates routing metadata, while Brennan owns consequential decisions. | Valid until expiry, correction, invalidation, or canonical-hash mismatch. | Requires evidence references, scope, validity, and a named curator/decision reference. |
| `role` | Role-specific procedures, temporary analysis pointers, and local retrieval aids. | Visible only to the named role unless an explicit handoff says otherwise. | Short-lived by default; must state expiry. | May become `project` only through a new evidenced project entry; copying a conclusion is prohibited. |
| `task` | One bounded workflow/task contract, receipts, dependencies, evidence pointers, stop condition, and handoff state. | Visible to the accountable task participants and independent reviewer where required. | Expires at terminal outcome plus defined audit retention; `BLOCKED`, `AMBIGUOUS`, and `INTERRUPTED` remain retrievable. | A terminal task receipt may support a `project` entry, but does not automatically create one. |

`project` is the only shared V20 knowledge scope. It intentionally does not replace platform-native memory, Kanban, or role instruction storage; adapters map their native stores to these semantic scopes.

## 4. Minimum provenance-rich index

The implementation target is one compact, append-oriented index with one record per claim or canonical artifact relationship. It should index only durable, decision-relevant material: the current admission decision, frozen contracts, independent reviews, artifact manifests, authority references, and final/invalidated receipts. It must not enumerate every log line or raw input file.

### Index entry schema [N]

```text
knowledge_entry = {
  schema_version: string,
  entry_id: string,                 # immutable
  revision_of_entry_id: string|null,
  scope: global|project|role|task,
  subject: string,                  # stable compact identifier, e.g. research.admission.broad-502
  classification: FACT|DECISION|CONTRACT|EVIDENCE|PROPOSAL|HANDOFF,
  status: VERIFIED|PARTIAL|UNVERIFIED|INVALID|SUPERSEDED|EXPIRED|UNAVAILABLE,
  statement: string,                # bounded, non-secret claim; no raw artifact copy
  canonical_artifacts: [artifact_ref],
  evidence_ids: [evidence_id],
  authority_reference: authority_ref|null,
  owner_role: role_id|null,
  task_id: string|null,
  valid_from_utc: timestamp,
  valid_until_utc: timestamp|null,
  review_after_utc: timestamp|null,
  correction_state: OPEN|CORRECTED|INVALIDATED|SUPERSEDED,
  correction_event_ids: [string],
  tags: [string],
  created_at_utc: timestamp,
  producer: producer_ref
}
```

Required rules:

- `subject` plus `scope` identifies the current lookup key; `entry_id` identifies an immutable revision.
- At least one `canonical_artifacts` item and one `evidence_id` are required for `FACT`, `DECISION`, and `CONTRACT` entries.
- `status=VERIFIED` is permitted only when every required canonical artifact is hash-verified and unexpired.
- A project entry about current research admission must link the exact review artifact, for example `reports/research/data_evaluation_admission_review_v1.md`, rather than restating a stale summary.
- An adapter may cache derived search text, but cache expiry cannot exceed the entry's `valid_until_utc` or `review_after_utc`.

### Canonical artifact reference [N]

```text
artifact_ref = {
  artifact_id: string,
  path_or_uri: string,
  sha256: string,
  media_type: string,
  role: source|contract|receipt|review|manifest|implementation_evidence,
  observed_at_utc: timestamp,
  immutable_or_versioned: boolean,
  access_class: public_to_v20|role_restricted|task_restricted,
  secret_scan_status: CLEAR|REJECTED|NOT_SCANNED,
  declared_valid_until_utc: timestamp|null
}
```

A missing or changed hash does not delete history; it marks dependent entries `UNAVAILABLE` until a curator verifies a new artifact revision. A directory, mutable database, or live service endpoint is not a canonical evidence artifact unless a separate immutable snapshot/manifest reference identifies its version.

## 5. Evidence, correction, invalidation, and expiry

### Platform-neutral evidence schema [N]

```text
evidence_record = {
  schema_version: string,
  evidence_id: string,              # immutable
  claim_subject: string,
  evidence_type: observation|test|review|receipt|manifest|authority,
  artifact: artifact_ref,
  locator: string,                  # line range, JSON path, table/query identifier, or stable section
  assertion: string,                # bounded statement supported by this evidence
  observed_by_role: role_id,
  observed_at_utc: timestamp,
  verification_method: hash|test|independent_review|manual_readonly_inspection,
  verification_result: PASS|FAIL|PARTIAL|NOT_RUN,
  limitations: [string],
  expires_at_utc: timestamp|null,
  supersedes_evidence_id: string|null,
  producer: producer_ref
}
```

Evidence must distinguish observation from interpretation. A worker may record an observed file hash, but a scientific conclusion remains `UNVERIFIED` until the required independent review evidence exists. `Risk` independently challenges evidence but cannot use an evidence record to authorize implementation or consequential action.

### Corrections and contradictions [N]

1. A correction appends `correction_event` with `prior_entry_id`, `new_entry_id`, reason, correcting evidence IDs, role, timestamp, and decision/authority reference when applicable.
2. An invalidation appends `status=INVALID` to a new revision and propagates `UNAVAILABLE` to every entry that names the invalidated evidence as required. It does not erase the original claim.
3. Contradictory verified entries for the same `scope + subject` are both marked `PARTIAL` with `contradiction_open=true` until an independent reviewer or Brennan-recorded decision resolves the conflict.
4. Consumers must retrieve the latest non-superseded revision and all open corrections before presenting a decision.
5. Any entry past `valid_until_utc` or `review_after_utc` is `EXPIRED` for operational use, while remaining auditable. No expiry may silently convert into a positive verdict.

## 6. Secret exclusion and safe content boundary

The index, evidence records, adapter caches, task packets, and portability exports must exclude credentials, tokens, passwords, cookies, `.env` contents, raw auth stores, private keys, broker/account identifiers, raw unredacted session transcripts, and protected raw data. An entry may reference a secret-safe artifact path only if its access class is restricted and the entry includes no secret value or recoverable fragment.

Before an item enters the shared index, the producing adapter must perform deterministic secret-pattern screening and reject `CLEAR` classification if screening is unavailable. A `REJECTED` item records only a non-sensitive rejection reason and a path-free opaque identifier; it is not copied into the index. Redaction is not permission to index an entire raw transcript or raw data artifact. Secret exclusion complements, but does not replace, platform access controls.

## 7. Portable task contract and receipt link

The G4/G8 lifecycle contract remains the authority for lifecycle semantics. The following portable task packet is the minimum adapter-neutral envelope; native Kanban cards, issue trackers, cron jobs, or orchestrators may store additional fields but must not reinterpret these ones.

```text
task_packet = {
  schema_version: string,
  workflow_id: string,
  task_id: string,
  parent_task_ids: [string],
  stage: ADMISSION|CONTRACT|IMPLEMENT|TRAIN|BACKTEST|REVIEW|NEXT,
  status: READY|ACTIVE|VERIFIED|FAILED|BLOCKED|INCONCLUSIVE|INTERRUPTED|AMBIGUOUS|REJECTED,
  title: string,
  source_authority: authority_ref,
  accountable_role: role_id,
  scope: {allowed_paths: [string], excluded_paths: [string], allowed_effect: none|read_only|approved_bounded},
  dependencies: [dependency_ref],
  acceptance_criteria: [string],
  stop_conditions: [string],
  required_evidence_ids: [string],
  knowledge_entry_ids: [string],
  authority_gates: [authority_gate],
  idempotency_key: string,
  created_at_utc: timestamp,
  expires_at_utc: timestamp|null
}
```

```text
authority_ref = {authority_type: brennan_instruction|approved_contract|review|none, reference: string, recorded_at_utc: timestamp}
authority_gate = {class: string, required: boolean, approval_reference: string|null, state: NOT_REQUIRED|PENDING|APPROVED|DENIED}
dependency_ref = {workflow_id: string, required_receipt_id: string, required_outcome: VERIFIED}
producer_ref = {platform: string, adapter_version: string, role_id: string}
```

A task packet must retain the authority reference, exact owner, evidence locations, acceptance criteria, and stop condition already required by the V20 role contracts. A `review` reference records evidence only; it is not an `approved_contract` or Brennan approval. Any denied-authority class remains `PENDING` and non-runnable until Brennan's exact-scope approval is recorded.

The portable task receipt is the lifecycle contract's receipt schema plus `knowledge_entry_ids`, `evidence_ids`, `artifact_sha256s`, and `portable_task_packet_sha256`. The adapter must bind those fields atomically with its native receipt or record `AMBIGUOUS`; a success message alone is not evidence.

## 8. Adapter obligations and minimum implementation boundary

A platform adapter must:

1. preserve immutable IDs, timestamps, canonical paths, hashes, and prior revisions;
2. resolve only the required `project`, role, and task scopes for the assigned role;
3. verify hashes before declaring an entry usable and surface status/limitations/corrections with every retrieval;
4. map native task/events/receipts to the portable schemas without losing native reference IDs;
5. keep role-local material isolated unless an evidenced project entry explicitly promotes it;
6. reject secret-bearing, hashless, expired-as-current, or authority-ambiguous entries; and
7. never create scientific truth, promote a model, schedule work, mutate protected data, or grant authority merely because an index entry exists.

The smallest safe implementation is one read-only project index plus schema validation and hash verification for a short allow-list of canonical V20 reports/receipts. It should not migrate memory providers, replace Kanban, synchronize platforms, ingest raw reports automatically, alter worker profiles, or create schedules. Any implementation requires a separately admitted exact-scope task and Brennan review of the allowed paths, secret-handling method, adapter ownership, and acceptance evidence.

## 9. Current gate

**Decision:** a compact provenance-rich shared project index and adapter-neutral task/evidence envelopes are defined.  
**Owner:** Brennan for design review and implementation authority; Product for a later, admitted non-consequential routing packet.  
**Current gate:** design contract review; existing research admission remains `NO-GO` and is not changed by this contract.  
**Blocker:** no approved implementation scope, storage location, secret-screening acceptance test, or independent verification receipt exists.  
**Next action:** Brennan may approve a separate minimum implementation task limited to an allow-listed index file, schema/hash validation, secret-rejection tests, and an independent Risk review; otherwise retain this proposal without runnable state.

READY_FOR_MINIMUM_IMPLEMENTATION
