# Cognee and AgentMemory evaluation notes

## Trigger

Use when comparing a graph/document-memory platform or a project named `agentmemory` for a Hermes deployment. The name `agentmemory` is ambiguous; identify the exact repository/package before making a recommendation.

## Source-inspection findings (July 2026)

### Cognee (`topoteretes/cognee`)

- Active Apache-2.0 graph + vector memory platform with explicit `remember`, `recall`, `forget`, and `improve` APIs; it supports document ingestion and structured Q&A, agent trace, feedback, and skill-run entries.
- Treat it as a candidate for a separate, project- or organization-scoped knowledge graph, not automatically as a personal-agent memory replacement.
- Its ready-made Claude Code integration captures prompts/tool traces/responses and injects retrieved context through lifecycle hooks. This is incompatible with a receive-only, explicitly searched vault model unless the integration is redesigned or tightly configured.
- No native Hermes memory-provider integration was verified during this review. Do not imply one exists without checking the current upstream integration catalog.
- If trialed, use a disposable Hermes profile and Cognee store; disable automatic capture/context injection and test only explicit `remember`/`recall` paths first.

### Hermes AgentMemory (`MukundaKatta/hermes-agentmemory`)

- The plugin advertises pull-model episodic recall, real deletes, and trace logging, but source inspection is mandatory before treating it as durable memory.
- At the reviewed revision, `AgentMemoryProvider` creates `EpisodicStore()` with the implementation's in-memory list default. It contains no persistence configuration or durable store wiring in the provider. Therefore it does **not** establish cross-process durable memory as written.
- It sends retrieved events to an Anthropic summarizer and requires an Anthropic API key; account for dependency, cost, and outbound data handling.
- The library's default store is explicitly in-memory; an optional production backend described upstream is not evidence that the Hermes plugin uses it.
- Reject it as a primary provider until a clean-session write → process restart → recall proof succeeds against a durable configured backend.

### Legacy PyPI `agentmemory` (`AutonomousResearchGroup/agentmemory`)

- This is a different project: a low-level ChromaDB/Postgres document-memory wrapper, last released in 2023 at the time of review.
- It is not a direct replacement for a governed provider with structured facts, provenance, scoped retrieval, corrections, and invalidation.

## Fit rule for a local second brain

For a user who wants a readable Obsidian workspace without automatic prompt leakage:

1. Keep one active durable provider.
2. Keep Obsidian as a local, explicit-search capture/reference layer.
3. Do not auto-promote notes or add lifecycle prefetch/sync hooks.
4. Require source-aware retrieval, correction/invalidation, deletion proof, project/worker isolation, and a fresh-session persistence test from any challenger.

A more capable graph or vector system is not better when it adds opaque automatic injection, hidden capture, or operational complexity without measured task improvement.

## Sources

- https://github.com/topoteretes/cognee
- https://docs.cognee.ai/
- https://github.com/MukundaKatta/hermes-agentmemory
- https://github.com/MukundaKatta/agentmemory
- https://pypi.org/project/agentmemory/
