# Whole-Stack Current-State Inventory

Use this reference when the user asks for the current stack, stackflow, APIs, AI providers, agents, technology, workflow, scheduling, or “everything.” The goal is an operationally truthful inventory, not a directory dump or a restatement of architecture docs.

## Evidence classes

Keep these separate throughout the audit:

1. **Declared design** — architecture docs, role descriptions, manifests.
2. **Configured capability** — config files, profile definitions, credential names, scheduler definitions.
3. **Installed capability** — dependency manifests and verified package/tool presence.
4. **Active runtime** — live processes/services, scheduler status, current provider calls.
5. **Produced evidence** — latest artifacts, receipts, ledgers, logs.
6. **Historical/retired surfaces** — compatibility code that is present but not authoritative.

Never promote one evidence class into another. A configured model is not an active worker; a scheduled task is not a successful run; a role file is not a provider call; code presence is not an active data source.

## Audit sequence

### 1. Establish authority and scope

- Read the project’s governance hierarchy first.
- Identify the canonical repository and active board/source of truth.
- Record the current operating mode and hard authority boundaries.
- If a secondary architecture document conflicts with the board, label it stale rather than averaging the two.

### 2. Map the end-to-end operational path

Trace the current path as:

```text
governance → ingest → storage/quality → features/factors/models
→ universe admission → portfolio/candidates → execution or preview
→ reconciliation → operator surface → review/promotion
```

For each node, identify the actual entrypoint, input, output, gate, and receipt.

### 3. Inventory APIs and data sources safely

- List environment-variable **names only**, never values.
- Trace each active producer to its real provider and endpoint family.
- Separate `active daily path`, `configured/report-only`, and `optional/historical` sources.
- Apply source-true naming: describe the provider that actually supplies the data, not a legacy factor or script label.
- Distinguish local cached/warehouse reads from live external calls.

### 4. Inventory AI providers and agents

Collect separately:

- Current interactive model/provider.
- Hermes/profile model declarations.
- Quota-router allocations.
- Role/SOUL descriptions.
- Provider-request ledger evidence.
- Worker activity/delegation evidence.

Report mismatches explicitly. The provider ledger is stronger evidence of what actually ran than a profile, SOUL file, quota table, or activity label.

### 5. Verify scheduling as an external system

Inspect both repository intent and the live scheduler:

- Hermes cron jobs.
- OS-native scheduler tasks.
- Gateway/service startup tasks.
- Last run, exit result, next run, and enabled/paused state.
- Whether every scheduled command target currently exists.
- Whether redundant schedules execute the same authority envelope.

A task pointing to a missing launcher is a current operational defect even if earlier runs succeeded.

### 6. Inspect current artifacts and receipts

Summarize the latest admitted data date, factor/model artifact state, candidate/basket, preview/order receipt, reconciliation, and worker/provider receipts. Prefer compact extraction over dumping large JSON.

Check that later reruns did not overwrite a previously green receipt with a contradictory status. When they did, explain the sequence and identify which contract disagreed.

### 7. Build a contradiction matrix

At minimum compare:

| Surface A | Surface B | Required check |
|---|---|---|
| Board authority | Execution guard | Same scope and envelope |
| Candidate producer | Submitter | Same symbol/side/notional provenance |
| Submitter | Reconciler | Same accepted envelope and identity |
| Formal policy | Scheduler pilot | Clear ownership and no contradictory enablement |
| Active operator declaration | Architecture docs | Same supported surface |
| Profile model | Role file | Same declared provider/model |
| Declared model | Provider ledger | Distinguish declaration from actual use |
| Scheduler task | Filesystem | Target exists now |
| Factor registry docs | Runtime registry | Same count and names |

### 8. Present the result in operational categories

Recommended report order:

1. One-paragraph executive summary.
2. ASCII end-to-end flow.
3. Governance and authority.
4. Active APIs/data sources; configured and historical sources separately.
5. Factors/models/portfolio methods.
6. AI providers and workforce hierarchy.
7. Actual worker-runtime truth.
8. Scheduling and redundancy.
9. Application/operator technology.
10. Storage and artifact roots.
11. Current operational snapshot.
12. Important inconsistencies.
13. One clear recommendation.

Keep the inventory comprehensive but avoid narrating every file read. Emphasize active/configured/historical classification and contradictions that affect operation.

## Verification checklist

Before finishing, confirm:

- Every “current” statement has live evidence.
- Secret values were never displayed.
- Role declarations were not presented as worker activity.
- Scheduler definitions were checked against current target files.
- The active operator surface was taken from the highest-authority source.
- Daily universe behavior was distinguished from historical PIT support.
- Paper/live, preview/submit, and application/pilot paths were not conflated.
- The final recommendation addresses the highest-risk broken handoff, not the largest code area.