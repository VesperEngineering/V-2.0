---
vesper_id: knowledge-governance
vesper_kind: skill
vesper_status: approved
vesper_scope: shared
title: V20 knowledge governance
tags:
  - knowledge
  - memory
  - governance
---
# V20 knowledge governance

## When to use

Use when proposing, reviewing, approving, rejecting, or retrieving durable V20 knowledge.

## Procedure

1. Admit only stable preferences, project invariants, verified reusable procedures, or durable lessons.
2. Verify the claim against current evidence and record provenance and evidence date.
3. Put drafts in `knowledge/inbox/`; never write a draft directly into runtime knowledge.
4. Reject task progress, session outcomes, temporary TODOs, run IDs, current blockers, credentials, secrets, and unsupported claims.
5. Move reviewed procedures or memories into `knowledge/skills/` or `knowledge/memory/` with `vesper_status: approved` only after explicit human approval.
6. Run `uv run --locked vesper-agent knowledge-sync`, inspect status, and verify retrieval for the intended role.

Knowledge supplies context only. Current instructions, repository state, policy, tests, evidence, and approval gates remain authoritative.
