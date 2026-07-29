# ADR-0003: Adaptive Knowledge Core

- Status: Accepted
- Date: 2026-07-29
- Owner: V20 operator
- Decision scope: Adaptive knowledge lifecycle and archive retrieval
- Extends: [ADR-0002](ADR-0002-obsidian-langgraph-knowledge.md)

## Context

ADR-0002 establishes repository-local Obsidian-compatible Markdown as the
canonical source for operator-authored knowledge. V20 also needs a bounded active
corpus, a reviewable way to surface durable candidates, and access to useful
older notes without silently changing their lifecycle state.

## Decision

The approved active corpus is capped at 3,000 complete Markdown source lines.
Line counting includes active note frontmatter and Markdown content; archived
notes do not consume the active budget. Active notes declare `pinned` or
`adaptive` retention. Only adaptive notes may be archived.

Archived memories and procedures live below `knowledge/archive/memory/` and
`knowledge/archive/skills/` with `vesper_status: archived` and adaptive
retention. They remain searchable as local, derived index content. A search or
run snapshot may retrieve at most two archived documents temporarily, within the
existing five-document and 8,000-character context limits. Retrieval never
changes a file's location, status, retention, authority, or active-line budget.

`knowledge-observe` creates an inbox candidate after an explicit request or
after three distinct observations of the same stable concept key. Candidate
creation is not approval. The operator alone approves, archives, permanently
reactivates, changes retention, or deletes knowledge; all file movement is
manual. Compaction and reactivation commands produce deterministic proposals
only. There is no controller delete or file-movement command.

Usage is credited only when a run is accepted. Mere selection, failed runs, and
unaccepted runs do not count as successful use.

The design adds no external service, embedding model, background scheduler, or
automatic file movement.

## Consequences

- The active corpus remains readable and bounded without discarding historical
  Markdown.
- Operators review candidates and lifecycle changes visibly in Obsidian or any
  Markdown editor.
- Archived context can inform a run without becoming active or gaining authority.
- The controller keeps derived indexes and lifecycle ledgers local and
  rebuildable; canonical Markdown remains authoritative.

## Alternatives considered

- Automatically promoting or moving agent-created candidates: rejected because
  durable knowledge requires operator review.
- Deleting low-use notes automatically: rejected because archival preserves
  inspectable history and deletion is an operator action.
- Embedding retrieval or a hosted service: rejected because ADR-0002's local,
  transparent lexical retrieval remains sufficient for this bounded corpus.

## References

- [ADR-0002: Obsidian and LangGraph Knowledge Standard](ADR-0002-obsidian-langgraph-knowledge.md)
- [Knowledge operator runbook](../runbooks/obsidian-knowledge.md)
- [Adaptive Knowledge Core design](../superpowers/specs/2026-07-28-adaptive-knowledge-core-design.md)
