---
name: vesper-issue-reporting
description: Use when an agent detects, investigates, repairs, verifies, or summarizes errors, bugs, stale data, scheduler failures, safety-gate failures, or operational problems in Vesper Quant or Vesper Swing.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [vesper, issue-tracking, operations, trading-safety, nightly-audit]
    related_skills: [operator-console-auditing, external-side-effect-safety, systematic-debugging]
---

# Vesper Issue Reporting

## Overview

Maintain evidence-backed, deduplicated issue registries for both Vesper projects. The registries record operational truth; they are not speculative backlogs and never grant execution authority.

Authoritative files:

- Vesper Quant: `D:/vesper/docs/ISSUES.md`
- Vesper Swing: `D:/swing-scope/docs/ISSUES.md`
- Combined generated briefing: `D:/vesper/docs/VESPER_DAILY_HEALTH.md`

## When to Use

Use this skill whenever work reveals a reproducible bug, error, stale artifact, failed test, missed scheduler run, dashboard contradiction, data-integrity problem, feed/broker evidence failure, or safety-gate failure. Also use it when verifying or closing an existing issue.

Do not create issues for ideas, feature requests, expected fail-closed blocks, or unsupported suspicions. A fail-closed block becomes an issue only when the underlying condition is erroneous or an expected recovery did not occur.

## Reporting Workflow

1. Read the appropriate `ISSUES.md` before adding anything. Search open and resolved entries for the same component, symptom, and evidence.
2. Reproduce or directly verify the condition using read-only probes whenever possible. Preserve exact command, timestamp, path, status, and concise output.
3. Classify the finding:
   - `Confirmed bug`: reproducible implementation defect.
   - `Operational failure`: expected scheduled/runtime outcome did not occur.
   - `Data integrity`: missing, stale, malformed, or contradictory authoritative data.
   - `Safety gate`: a gate failed incorrectly, was bypassed, or lacked evidence.
   - `Needs investigation`: strong evidence exists but root cause is not confirmed.
4. Deduplicate. If an existing issue matches, update `Last confirmed`, evidence, and status instead of creating a new entry.
5. Create a stable ID only for a new issue: `VQ-YYYYMMDD-NNN` for Quant or `VS-YYYYMMDD-NNN` for Swing. Choose the next unused sequence for that date.
6. Record operational impact and the safest next action. If inputs or authority are uncertain, explicitly state `Fail closed`.
7. Close only after the fix is exercised and the original failure is no longer reproducible. Record tests/probes and the verification timestamp.
8. **Reconcile the fact-base mirror in the same candidate.** If `docs/VESPER_FACT_BASE.json` includes the issue under `open_issues`, remove that exact entry when the matching `docs/ISSUES.md` block becomes `Verified closed`. The documentation-freshness parser excludes closed issue blocks; leaving the fact-base entry causes a checked-in consistency failure. Never remove an entry merely because it is old or quiet—only pair it with an evidence-backed closure.
   ```bash
   python -m pytest tests/test_documentation_freshness.py tests/test_operator_docs.py -q --basetemp=<external-same-drive-temp>
   python scripts/validate_documentation_freshness.py --root .
   ```

Completion criterion: every reported issue has unique identity, current status, direct evidence, operational impact, and a safe next action; no duplicate was introduced.

## Required Issue Schema

```markdown
## VQ-YYYYMMDD-NNN — Concise factual title

- Project: Vesper Quant | Vesper Swing
- Severity: Critical | High | Medium | Low
- Status: Open | Reproduced | Fix in progress | Tests passing | Awaiting review | Verified closed
- Type: Confirmed bug | Operational failure | Data integrity | Safety gate | Needs investigation
- First observed: ISO timestamp with timezone
- Last confirmed: ISO timestamp with timezone
- Component: Exact subsystem
- Detection source: Agent/session/job/probe
- Evidence:
  - Exact artifact, command, log line, API response, or failing test
- Operational impact:
  - Concrete consequence; do not inflate
- Safe next action:
  - Smallest safe investigation or repair step
- Execution impact:
  - `None`, or exact fail-closed trading restriction
- Resolution:
  - Pending, or fix plus verification evidence
```

## Severity Rules

- `Critical`: unsafe external mutation, execution-gate bypass, account/order ambiguity, or corruption of authoritative state.
- `High`: trading must remain blocked, a required scheduled pipeline failed, authoritative data is stale/corrupt, or operator health is materially false.
- `Medium`: degraded operation with a safe fallback, isolated failed test, or material observability defect.
- `Low`: minor defect with no trading, data-authority, or operator-decision impact.

Never raise severity merely to attract attention.

## Nightly Audit Boundary

Nightly audits are read-only except for updating the three Markdown registries. They may inspect repository state, tests already recorded, logs, receipts, scheduler state, databases in read-only mode, dashboard/API health, artifact freshness, and broker/feed evidence that does not mutate remote state.

Nightly audits must not:

- Submit, cancel, replace, preview-submit, or liquidate orders.
- Trigger rebalance, scoring, ingestion, training, deployment, promotion, or scheduler mutation.
- Change factor weights, risk limits, targets, provider configuration, credentials, or dependencies.
- Mark a problem resolved from code inspection alone.
- Treat a historical `OK` log line as current health.
- expose secrets, account identifiers, or credential values in issue files.

If a probe might mutate external or canonical state, skip it and record the evidentiary limitation.

## Daily Health Briefing

Generate `VESPER_DAILY_HEALTH.md` from the two registries and current read-only evidence. Keep it concise:

1. Timestamp and overall state: `HEALTHY`, `DEGRADED`, or `BLOCKED`.
2. Immediate attention, ordered by severity then age.
3. Newly detected issues.
4. Resolved and independently verified issues.
5. Quant readiness and Swing readiness separately.
6. Evidence limitations and skipped unsafe probes.

`HEALTHY` requires no open Critical/High issue and current evidence for required systems. Missing evidence is not green.

## Repair Boundary

Agents may repair ordinary engineering defects only when authorized by the current task and repository rules. Trading logic, factor behavior, portfolio construction, risk limits, broker paths, order lifecycle, scheduler configuration, and promotion remain separately reviewed. Discovery does not grant repair authority.

Use the lifecycle:

`Open -> Reproduced -> Fix in progress -> Tests passing -> Awaiting review -> Verified closed`

A code change or passing focused test alone is not closure; rerun the original failing probe and relevant regression suite.

## Supporting References

- For the reusable multi-repository cron design—separate read-only audit and bounded repair jobs, `context_from` chaining, `workdir` behavior, CLI/Desktop profile continuity, repair eligibility, and review ownership—read `references/nightly-audit-repair-architecture.md`.
- For Password-logon Windows tasks—credential identity, S4U limits, protected runtime deployment, ignored/static data, SQLite state transfer, safe `schtasks` diagnostics, installed-task inspection, and receipt-backed cutover—read `references/windows-task-scheduler.md`.

## Common Pitfalls

- Free-form append-only notes create duplicates and stale claims. Follow the schema and update existing entries.
- A single agent that discovers, repairs, and closes its own finding collapses authority boundaries; separate audit, bounded repair, and independent closure.
- A cron `workdir` loads only that repository's context. Explicitly read the other repository's rules during multi-project audits.
- Local cron delivery is durable but does not create a live CLI notification; verify through the generated files or cron status.
- Existing interactive agents do not automatically receive a newly created skill or changed project context mid-session; cron runs are fresh and new CLI sessions should start at the repository root.
- Expected fail-closed behavior is not itself a bug.
- Browser refresh age is not source-data age.
- A successful manual command does not prove unattended scheduling. Source tests, successful registration, task invocation, and end-to-end installed-runtime evidence are separate gates.
- A Windows Hello PIN is not the password credential required by Task Scheduler `Password` logon. Establish the exact local/Microsoft/work principal before retrying rejected credentials, and never collect the password in chat or command history.
- A protected Git snapshot can still be operationally incomplete when ignored static inputs, historical lookback databases, or weighted-factor dependencies were omitted. Inventory downstream reads before cutover instead of repairing one missing path per run.
- Do not pause redundant scheduling until the installed task has `Last Result: 0`, a canonical success log, matching PASS receipts, and no forbidden side effect.
- **A scheduled task showing `Status: Ready` does not prove it is executing.** Both `Status: Ready` and `Last Result: 1` can coexist — the scheduler considers the task enabled but the OS cannot launch the referenced action file (missing binary, deleted wrapper, renamed script). Cross-check the exact action path against the filesystem and correlate `Last Result` with pipeline logs.
- **Cross-document date reconciliation**: when a pipeline is stale, check every status/fact document independently — not just the most obvious one. `STATUS.md` may have been corrected (e.g., `local_ohlcv_date: 2026-07-10`) while `VESPER_FACT_BASE.json` still shows a false-green date (`local_ohlcv_date: 2026-07-13`). A single corrected document does not mean the truth is propagated. Verify each document's claimed dates against the actual data source (DB max, file timestamp, API response).
- Old broker/feed snapshots do not prove current connectivity.
- Do not let the same agent silently discover, reinterpret, repair, and close a safety-critical issue in one pass.

## Verification Checklist

- [ ] Correct project registry was read first.
- [ ] Finding is evidence-backed and deduplicated.
- [ ] ID, severity, type, status, timestamps, component, impact, and safe next action are present.
- [ ] No secrets or sensitive account details were recorded.
- [ ] External execution and scheduler mutation remained disabled.
- [ ] Closed issues include rerun evidence for the original failure.
- [ ] Scheduler closure, when applicable, verifies the installed task definition, `Last Result: 0`, canonical success log, required runtime state, and downstream PASS receipts before redundant coverage is paused.
- [ ] Combined health does not claim green when evidence is missing or stale.
