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
- `memory/v20-core/`: active shared V20 memory. Keep this small, reviewed, and
  useful at run creation; the controller scans it recursively.
- `skills/v20/`: active shared V20 procedures and navigation notes.
- `inbox/`: drafts awaiting human review; never synchronized.
- `inbox/v20-dream-gate/`: legacy review material; new ordinary dream learnings
  are applied directly to active memory or skills.
- `dreams/`: cold-store Dream Gate reports and applied-change receipts; never
  synchronized as runtime knowledge.
- `sessions/`: controller-captured redacted V20 event transcripts used as dream
  inputs; external Codex chat, full system prompts, hidden reasoning, credentials,
  and raw protected data are not captured; never synchronized.
- `working-memory/`: controller-managed per-agent cores, archives, and change
  history; never synchronized as active knowledge.
- `templates/`: authoring templates; never synchronized.

## Memory tiers

Active memory is the automatically maintained subset under `memory/` and
`skills/`. Cold transcripts remain searchable history, while Dream Gate
consolidates stable learnings into active notes automatically. Dreaming is a
session-close/background consolidation pass, not a scheduler.
Each agent working-memory core is capped at 2,000 words. The combined approved
active knowledge corpus is capped at 3,000 source lines; synchronization fails
closed when the limit is exceeded.

## Authority

Knowledge is context. Current user instructions,repository state, policy, tests, 
typed evidence, approval gates, and risk limits always outrank a note in this vault. 
Specialists cannot read or write the vault directly.

See [the operator runbook](../docs/runbooks/obsidian-knowledge.md) for authoring,
approval, synchronization, retrieval, and recovery.
