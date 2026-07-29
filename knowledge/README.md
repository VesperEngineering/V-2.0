# V20 knowledge vault

This directory is V20's canonical, repository-owned source for durable agent
memories and reusable procedures. It is an ordinary Markdown tree that can be
opened as an Obsidian vault; Obsidian is optional and is not a runtime
dependency.

Only notes under `memory/` and `skills/` with valid V20 frontmatter and
`vesper_status: approved` enter runtime knowledge. Drafts belong in `inbox/`.
The controller reads this vault, synchronizes approved notes into a rebuildable
LangGraph Store/SQLite FTS index, and creates immutable role-scoped snapshots at
run creation.

## Layout

- `memory/`: durable facts, preferences, decisions, and conventions.
- `skills/`: reviewed procedures for agents. These are knowledge notes, not
  executable Codex skill packages.
- `inbox/`: drafts awaiting human review; never synchronized.
- `templates/`: authoring templates; never synchronized.

## Authority

Knowledge is context, not proof or permission. Current user instructions,
repository state, policy, tests, typed evidence, approval gates, and risk limits
always outrank a note in this vault. Specialists cannot read or write the vault
directly.

See [the operator runbook](../docs/runbooks/obsidian-knowledge.md) for authoring,
approval, synchronization, retrieval, and recovery.
