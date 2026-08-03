---
vesper_id: v20-bounded-agent-research
vesper_kind: skill
vesper_status: approved
vesper_scope: shared
title: V20 bounded agent research and knowledge guardrails
tags: [agents, quant, research, knowledge, governance]
---
# V20 bounded agent research and knowledge guardrails

1. Treat `vesper/data/massive/` and `vesper/data/model_research/` as protected read-only inputs.
2. Verify data identity, coverage, point-in-time availability, adjustment state, and model metadata.
3. Require chronological evaluation, leakage controls, a simple baseline, and exact artifact hashes.
4. Treat missing, stale, conflicting, or provenance-unbound evidence as unavailable.
5. Keep research separate from promotion, capital, risk, trading, and deployment authority.
6. Admit only stable, verified, reusable knowledge with provenance and an evidence date.
7. Put drafts in `knowledge/inbox/`; never write model output directly into approved knowledge.
8. Never store task progress, temporary TODOs, credentials, secrets, or unsupported claims.

Knowledge supplies context only. Current instructions, policy, tests, evidence, and approval gates
remain authoritative.
