---
name: vesper-autonomous-workflow
description: Use when coordinating normal Vesper engineering or documentation work across agents and worktrees. Keep work moving autonomously and apply one review gate only at a real decision point.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [vesper, worktrees, delegation, autonomy, review]
    related_skills: [surgical-engineering, governed-repo-contribution, requesting-code-review]
---

# Vesper Autonomous Workflow

## Overview

Normal Vesper work should flow through an assigned worktree without procedural churn. A checkpoint is for a real decision—commit, merge, deployment, or an explicitly requested independent review—not a recurring handoff ritual.

This skill preserves authority gates for money, broker/order activity, risk, scheduler, provider, promotion, deployment, and secrets. It does not add freeze gates to ordinary local engineering, documentation, validation, or UI work.

## When to Use

Use when:

- handing a Vesper task between agents or Hermes sessions;
- operating an isolated Vesper worktree with uncommitted changes;
- preparing a candidate for review or commit;
- deciding whether a changed patch requires investigation.

Do not use it to delay ordinary editing, test runs, or an authorized repair solely because a previous patch ID changed.

## Operating Rules

1. **Assign one worktree and one active task owner.**
   Keep normal source and test changes in that worktree. Preserve unrelated pre-existing changes.

   Completion criterion: the agent can name the worktree, task scope, and files it owns.

2. **Let the owner iterate.**
   The owner may inspect, edit within scope, add regressions, and run focused/full checks without requesting a new checkpoint after every result.

   Completion criterion: requested behavior and its validation are complete, or a concrete blocker is reported.

3. **Use patch identity only as a diagnostic.**
   Compare status/diff/patch identity when there is actual evidence of concurrent writers, an unexpected file, a scope breach, or a reviewer needs provenance. A changed patch after an authorized repair is expected, not a reason to stop.

   Completion criterion: unexpected changes are either attributed to an authorized task or isolated before further work.

4. **Take one decision checkpoint.**
   Request an independent review only when the candidate is ready for a commit/merge decision or when the user explicitly asks for review. Do not repeatedly freeze the same active task between repair agents.

   Completion criterion: the reviewer receives the current worktree, intended scope, required validation, and no stale patch-ID requirement.

5. **Classify proposals before routing.**
   Do not use a Kanban status name such as `blocked` or `triage` as the authority boundary: dispatcher/decomposer behavior may make those cards runnable. Classify each proposal against the board/manifests before any Kanban action:
   - an explicitly allowlisted, non-gated local engineering/validation/report task may be created and dispatched autonomously in its isolated worktree;
   - an unknown, mixed, or strict-authority proposal is `gated_review_only` and must stay outside the executable Kanban path until its exact approval contract is satisfied.

   Completion criterion: the proposed route is bound to an authority class, source evidence, allowed scope, and denied capabilities before task creation.

6. **Keep authority gates separate and approval-parity bound.**
   Human approval remains mandatory for broker/account/order activity, risk/target changes, scheduler actions, provider/entitlement changes, promotion, deployment, and secrets. A gated request must bind its source/candidate identity, exact action and scope, allowed tools/paths, expiry, requester, reviewer, and denied capabilities. VOT and Telegram must consume the same append-only approval record so the decision has parity across both surfaces. A stale, altered, self-approved, or unauthenticated record is non-authorizing; a human label alone is an attestation, not execution authority.

   Completion criterion: the final report distinguishes autonomous non-gated engineering from separately closed operational authority.

7. **Review every agent submission.**
   Before an agent submits a candidate for a commit, merge, integration, or other decision, require an independent review receipt bound to the exact candidate SHA/diff and executed validation. The reviewer reports findings; the owner makes any repair and returns once for final review. Do not use review to create duplicate routine freezes during ordinary implementation.

   Completion criterion: the submission packet names the frozen candidate identity, reviewer, review result, and actual checks.

## Handoff Pattern

A normal handoff should state only:

- worktree and task objective;
- explicitly approved edit scope;
- constraints and closed authority domains;
- required tests/checks;
- stop condition: completion, a real blocker, or a scope/authority breach.

Avoid: repeated demands to freeze, re-identify, or re-approve a candidate unless its current diff cannot be attributed to authorized work.

## Publishing and Integration

A commit, a pushed branch, a pull request, and default-branch integration are different actions. Say which action is happening before doing it.

- A commit records the change locally.
- A remote branch is the normal Git ref that makes an isolated-worktree commit reachable after a push; pushing it does not create a pull request.
- A GitHub “create pull request” URL is an optional host hint, not an action taken. Do not present it as though a PR exists.
- If the user wants direct default-branch integration and the remote default branch advanced past the candidate base, first integrate in a clean worktree (for example, cherry-pick onto the current remote default), validate the result, then push the default branch. Do not imply that a branch publish already performed this integration.

Completion criterion: the report names the commit SHA, remote ref, whether a PR exists, and whether the default branch contains the change. See `references/git-publication-state.md` for precise publication-state wording.

## Common Pitfalls

1. **Treating every agent handoff as release governance.**
   Fix: continue normal work; reserve review gates for commit/merge/deploy decisions.

2. **Blocking on an old patch ID after an authorized repair.**
   Fix: inspect the current delta. Continue when it matches the authorized repair scope.

3. **Using process controls as a substitute for authority controls.**
   Fix: preserve strict operational gates while keeping non-gated engineering autonomous.

4. **Making a reviewer repair the candidate.**
   Fix: reviewer reports findings; the active owner makes the smallest repair and returns for one final review.

## Verification Checklist

- [ ] Active worktree and scope are clear.
- [ ] Normal iteration was not blocked by routine patch movement.
- [ ] Any unexpected diff was attributed or isolated with evidence.
- [ ] Review occurred only at an explicit decision point.
- [ ] Operational authority boundaries remained independently gated.
- [ ] Final report states the current candidate, tests actually run, and remaining gates.
