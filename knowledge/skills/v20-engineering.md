---
vesper_id: v20-engineering
vesper_kind: skill
vesper_status: approved
vesper_scope: v20-development
title: V20 engineering workflow
tags:
  - engineering
  - verification
  - worktrees
---
# V20 engineering workflow

## When to use

Use for code, configuration, tests, documentation tied to code, or repository cleanup.

## Procedure

1. Read the nearest `AGENTS.md` and current source. Surface ambiguity and tradeoffs; never choose silently.
2. Inspect Git status and preserve unrelated changes. Use an isolated worktree when ownership overlaps.
3. State the bounded outcome, assumptions, expected files, authority limits, and verification.
4. Make the minimum sufficient change. Match existing style; avoid speculative abstractions, configurability, impossible-case handling, and adjacent cleanup.
5. Remove only imports, variables, functions, or files made obsolete by this change.
6. Run focused tests first, then the smallest broader check justified by impact.
7. Inspect the final diff and report actual evidence, remaining risk, and the next safe action.

Never treat tests, a specialist response, or a commit as deployment, trading, model-promotion, or approval authority.
