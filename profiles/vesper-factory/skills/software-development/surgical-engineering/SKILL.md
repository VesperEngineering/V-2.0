---
name: surgical-engineering
description: Use when implementing or modifying code, tests, or project configuration. Make evidence-based, minimal-scope changes with explicit success criteria; pair with verification before completion.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [software-development, scope-control, minimal-diffs, simplicity, verification]
    related_skills: [test-driven-development, requesting-code-review, systematic-debugging, plan]
---

# Surgical Engineering

## Overview

Make the smallest evidence-based change that solves the requested problem. Do not turn a focused task into a cleanup, redesign, or speculative platform.

This skill governs engineering judgment and edit scope. It does **not** replace:

- `test-driven-development` for strict RED → GREEN → REFACTOR work.
- `systematic-debugging` for root-cause investigation.
- `requesting-code-review` for pre-commit security, lint, test, and independent-review gates.
- `plan` when the user asks for a written plan rather than implementation.

## When to Use

Use before editing production code, tests, build files, or project configuration, especially when the task is a bug fix, a small feature, a refactor, or a request to "clean up" code.

Do not use it to authorize broad refactors, deletion of existing code, or changes outside the request. Those need explicit user scope and any applicable specialized skill.

## 1. Establish the Change Contract

Before editing:

1. Read the relevant implementation, its tests, and project instructions.
2. Define the requested behavior and a checkable success criterion.
3. Identify the smallest likely file/function surface.
4. Resolve ordinary implementation details from repository evidence: existing callers, tests, conventions, documentation, and nearby patterns.

State material assumptions only when they affect observable behavior, public interfaces, data formats, safety, cost, or scope. Do not narrate routine coding decisions.

If an unresolved ambiguity materially changes behavior, scope, risk, or an irreversible choice:

- name the alternatives and their consequence;
- recommend the evidence-supported, reversible default when one exists; and
- ask the user only when repository evidence cannot resolve it safely.

Do not silently choose among materially different interpretations.

### Completion criterion

Do not begin implementation until the requested behavior, relevant boundary, and verification method are known.

### Checkpoints Are Proportional, Not Stop Signs

Use a worktree and a short identity record to protect handoffs, independent review, and commit decisions. Do **not** turn routine active engineering into repeated freeze/confirm cycles.

- Let the designated agent make the approved bounded repair and run its checks without requiring a new patch-ID confirmation after every report.
- Take one explicit checkpoint when the work changes hands, reaches independent review, or is ready to commit.
- If a diff unexpectedly changes while another agent is active, inspect the new paths and timestamps once. Continue when the added changes are within the authorized repair scope; stop only for unrelated or unexplainable changes.
- Describe a candidate as “ready for review” rather than “frozen” unless immutability is actually required for a commit, release, or external approval.

This preserves fail-closed review boundaries without adding avoidable orchestration churn.

## 2. Keep the Design Simple

Implement only what the request requires.

- Prefer direct code over a new abstraction for a one-use case.
- Do not add speculative features, configuration, extension points, compatibility layers, or generalized frameworks.
- Reuse an existing local helper or project pattern when it fits without distorting the requested behavior.
- Introduce an abstraction only when it is required by the task or removes demonstrated duplication in the change being made.
- Preserve realistic error handling at user-input, filesystem, database, network, subprocess, and external-service boundaries.
- Do not add defensive branches for hypothetical states unsupported by the codebase or task.

Ask: **Would the existing project style support a smaller direct implementation?** If yes, take that path.

### Completion criterion

Every new function, parameter, branch, dependency, and configuration option must have a direct, present-tense reason traceable to the request.

## 3. Make Surgical Diffs

Touch only code required for the requested behavior, its verification, and artifacts made obsolete by your own change.

When editing existing code:

- Do not reformat, rename, modernize, refactor, or rewrite adjacent code unless necessary for the requested behavior.
- Match local style, naming, and architecture even when another style seems preferable.
- Do not remove pre-existing dead code, imports, tests, comments, or configuration merely because it is nearby. Report it separately if relevant.
- Remove imports, variables, branches, helpers, tests, or documentation made unused **by this change**.
- Preserve line structure when it is semantically correct; do not churn expressions merely to restate them.

Use a changed-line test before completion:

> Each changed line must trace directly to the user request, a necessary regression/behavior test, or removal of an artifact introduced or obsoleted by this change.

### Completion criterion

Inspect the final diff. Revert any unrelated or style-only change before verification.

## 4. Execute Toward a Verifiable Goal

Translate the request into observable checks, not vague intentions.

- **Bug fix:** reproduce the defect in a focused test or executable check, then make it pass.
- **Behavior change:** add or update a test/check that proves the requested behavior and the relevant failure boundary.
- **Refactor:** prove behavior remains intact with the relevant tests before and after the edit.
- **Multi-step work:** make a concise execution list where every step includes its verification, for example:

```text
1. Reproduce invalid-ledger behavior in a focused test → verify expected failure
2. Make the smallest loader change → verify focused test passes
3. Run affected suite and configured static checks → verify no regression
```

Use strict test-first cycles when `test-driven-development` applies. For a root-cause investigation, load `systematic-debugging` before attempting a fix.

### Completion criterion

Every implementation step has an observable pass/fail check. "Looks right" and unrecorded manual inspection are not verification.

## 5. Verify and Report Truthfully

Before declaring substantive work complete, load and follow `requesting-code-review`.

At minimum:

1. Inspect the final diff for scope and accidental churn.
2. Run the smallest relevant tests, then the required project suite when practical.
3. Run configured formatter, linter, and type checks when available.
4. Distinguish actual results from assumptions.

Report:

- files changed and why;
- verification commands actually run and their actual result;
- required checks not run, why, and the remaining gate;
- any separately observed unrelated debt, without modifying it.

Never call work verified, ready, or complete when a required check was skipped, failed, or was not available. State the open gate precisely.

## Common Pitfalls

1. **Questioning routine details.** Inspect repository evidence first; ask only about material ambiguity.
2. **Solving a future problem.** Remove speculative code and implement the current requirement only.
3. **Cleanup disguised as implementation.** Revert unrelated churn; make it a separate, explicitly scoped task.
4. **Removing error handling as "impossible."** Keep handling for real external boundaries; avoid only unsupported hypothetical cases.
5. **Claiming validation without output.** A check not run is an open gate, not a passing result.
6. **Using this skill as a substitute for TDD or code review.** Load the specialized companion skill rather than duplicating its workflow.
7. **Trusting a targeted patch without rereading its enclosing block.** Fuzzy patch tools can match a repeated fragment and accidentally drop neighboring lines, especially after several sequential edits in one function. After every syntax-sensitive patch, immediately read the enclosing function block and run the narrowest syntax check (for Python, `python -m py_compile <file>`). If a patch reports an unexpected diff, stop and repair the full local block before making any further edit; never stack patches on an unverified partial edit.

## Verification Checklist

- [ ] Relevant implementation, tests, and project instructions were inspected.
- [ ] Requested behavior and success criterion are concrete and checkable.
- [ ] Material ambiguities were resolved from evidence or surfaced to the user.
- [ ] Every changed line is in scope.
- [ ] No speculative feature, abstraction, configuration, or unrelated cleanup was added.
- [ ] Tests and static checks were run or an exact remaining gate was reported.
- [ ] Final report distinguishes verified facts from assumptions.
