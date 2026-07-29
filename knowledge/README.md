# V20 knowledge vault

This directory is V20's canonical, repository-owned source for durable agent
memories and reusable procedures. It is an ordinary Markdown tree that can be
opened as an Obsidian vault; Obsidian is optional and is not a runtime
dependency.

Only notes under `memory/` and `skills/` with valid V20 frontmatter and
`vesper_status: approved` are active runtime knowledge. Drafts belong in
`inbox/`; archived notes belong under `archive/` with `vesper_status: archived`.
The controller reads this vault, synchronizes the validated inventory into a
rebuildable LangGraph Store/SQLite FTS index, and creates immutable role-scoped
snapshots at run creation.

## Layout

- `memory/`: durable facts, preferences, decisions, and conventions.
- `skills/`: reviewed procedures for agents. These are knowledge notes, not
  executable Codex skill packages.
- `inbox/`: drafts awaiting human review; never synchronized.
- `archive/memory/` and `archive/skills/`: retained adaptive notes with
  `vesper_status: archived`; searchable but outside the active line budget.
- `raw/`: non-authoritative source material; never synchronized.
- `wiki/`: human navigation notes; never synchronized.
- `templates/`: authoring templates; never synchronized.

## Active budget and retrieval

Active `memory/` and `skills/` notes are capped at 3,000 complete Markdown
source lines. The count includes frontmatter and Markdown content for active
notes; archive, inbox, raw, wiki, templates, and README files do not consume it.
`knowledge-sync` rejects an over-budget active corpus before mutating derived
state.

Archive retrieval is temporary: a role-scoped search may select at most two
archived documents within the existing five-document and 8,000-character context
limits. Retrieval does not move a note, change its status or retention, alter the
active budget, or grant authority.

## Human-governed lifecycle

Submit observations with `knowledge-observe`. An explicit observation creates a
candidate immediately; otherwise the same stable concept key needs three distinct
source references. The controller creates or updates only an inbox candidate.
Operators review candidates in Obsidian or another Markdown editor and manually
move files to approve, archive, or reactivate them. Operators alone may approve,
archive, permanently reactivate, change retention, or delete a note. There is no
controller command that deletes or moves knowledge files.

Usage is credited only after a run is accepted; selection for a snapshot is not
success credit. Compaction and reactivation commands produce review proposals,
not filesystem changes.

## Authority

Knowledge is context, not proof or permission. Current user instructions,
repository state, policy, tests, typed evidence, approval gates, and risk limits
always outrank a note in this vault. Specialists cannot read or write the vault
directly.

See [the operator runbook](../docs/runbooks/obsidian-knowledge.md) for authoring,
approval, synchronization, retrieval, compaction, and recovery.
