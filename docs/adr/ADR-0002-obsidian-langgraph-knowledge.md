# ADR-0002: Obsidian and LangGraph Knowledge Standard

- Status: Accepted
- Date: 2026-07-28
- Owner: V20 operator
- Decision scope: Durable agent memories and reusable procedures

## Context

V20 needs durable, reviewable agent knowledge without making an agent runtime,
hosted memory service, or opaque vector database the source of truth. Operators
must be able to inspect and edit the corpus with ordinary tools, while a run must
see stable role-scoped context after interruption and resume.

Receipt-derived `MemoryRecord` entries already capture validated workflow
outcomes. They are authoritative runtime records, but they are not an ergonomic
human knowledge base and must not be conflated with operator-authored guidance.

## Decision

The repository-local `knowledge/` directory is the canonical source for
operator-authored V20 memories and procedures. It is standard Markdown and may
be opened directly in Obsidian. No Obsidian plugin, MCP server, cloud sync,
external vault, or additional credential is required.

The legacy `profiles/vesper-factory` bundle and any external vault configured by
it are outside the native platform profile catalog. This decision does not read,
modify, or migrate either one.

Only valid notes under `knowledge/memory/` and `knowledge/skills/` with
`vesper_status: approved` are admitted. Each note has a stable ID, kind, scope,
title, optional tags, relative source path, and source SHA-256. Allowed scopes
are `shared`, `v20-product`, `v20-development`, and `v20-risk-review`.

The controller synchronizes approved documents into LangGraph Store and rebuilds
a dedicated SQLite FTS5 index. Both are derived local state. Deletion from the
canonical vault removes the derived Store record on the next successful sync.
Malformed or duplicate approved notes fail synchronization before mutations.
If a Store mutation or FTS rebuild fails, synchronization restores both derived
corpora to their complete previous state before returning the failure.

At run creation, the controller retrieves at most five matching documents and
8,000 content characters per specialist role, then persists an immutable
`KnowledgeContext` snapshot in LangGraph Store. Resume reads only that snapshot;
it does not reread changed vault contents. Historical runs without a snapshot
receive no injected knowledge.

Specialists receive the selected documents inside a clearly marked
`<v20_knowledge>` context section with source path and hash provenance. They have
no direct filesystem access to `knowledge/`, and notes cannot override current
instructions, policy, permissions, evidence, validation, risk limits, or human
approval.

Receipt-derived runtime memories remain separate. This ADR does not turn an
operator-authored note into evidence or authorize automatic writing back to the
vault.

## Consequences

- Knowledge is human-readable, versioned, portable, and usable without Obsidian.
- Runtime retrieval is local, deterministic in scope, and rebuildable.
- Run context remains stable across resume even when the vault changes.
- Approval is intentionally manual; agents may propose drafts in `inbox/` but
  cannot silently promote them.
- FTS5 is the initial lexical retrieval method. Embeddings or a vector index may
  be added only after an evidence-backed retrieval benchmark demonstrates need.
- Operators must back up canonical Markdown through normal repository practices;
  the derived databases are not the backup authority.

## Alternatives considered

- External or cloud Obsidian integration: rejected because local Markdown is
  sufficient and minimizes authority and credential surface.
- Hosted memory services: rejected because they make V20 knowledge dependent on
  external state and billing.
- SQLite or a vector database as canonical storage: rejected because it weakens
  human review and portability.
- Reading the live vault on every specialist turn: rejected because a resumed run
  could silently receive different context.
- Automatically approving model-generated memories: rejected because generation
  is not validation or operator consent.

## References

- [Knowledge operator runbook](../runbooks/obsidian-knowledge.md)
- [Detailed design](../superpowers/specs/2026-07-28-obsidian-langgraph-knowledge-standard-design.md)
- [Native LangGraph platform](ADR-0001-native-langgraph-platform.md)
