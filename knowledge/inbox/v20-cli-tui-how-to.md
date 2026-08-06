---
vesper_id: v20-cli-tui-how-to
vesper_kind: skill
vesper_status: candidate
vesper_scope: shared
title: V20 CLI and TUI how-to guide
tags:
  - v20
  - cli
  - tui
  - operator
---

# V20 CLI and TUI how-to guide

> Draft guide. The CLI is runnable in this checkout. The TUI is still planned
> and is not an installed or runnable command here.

## 1. Start here

Open PowerShell at the repository root:

```powershell
Set-Location C:\Users\bgonn\Desktop\v20
uv run --locked vesper-agent --help
```

The command is `vesper-agent`. Run global options before the command:

```powershell
uv run --locked vesper-agent --json active
uv run --locked vesper-agent --knowledge-root knowledge knowledge-status
```

Use `--json` for scripts or a future TUI adapter. Do not put secrets in
commands, notes, logs, screenshots, or output files.

## 2. Which interface to use

| Need | Use |
| --- | --- |
| Inspect one state, run, receipt, or evidence record | CLI |
| Create, resume, approve, reject, or cancel a run | CLI, with the required explicit authority |
| Search or synchronize approved vault knowledge | CLI |
| See a live read-only summary | Planned TUI |

The Python controller remains authoritative. A screen, proposal, approval, or
receipt does not by itself mean that a broker position, order, model, or
portfolio changed.

## 3. Safe read-only inspection

Run these from the repository root:

```powershell
# Running or crash-interrupted runs
uv run --locked vesper-agent active

# Runs waiting for explicit operator approval
uv run --locked vesper-agent approvals

# Inspect one run
uv run --locked vesper-agent status <run-id>
uv run --locked vesper-agent receipts <run-id>
uv run --locked vesper-agent evidence <run-id>

# Agent work and routes
uv run --locked vesper-agent agent-roster
uv run --locked vesper-agent agent-queue

# Knowledge index
uv run --locked vesper-agent knowledge-status
```

For machine-readable output:

```powershell
uv run --locked vesper-agent --json active
uv run --locked vesper-agent --json status <run-id>
```

`active`, `approvals`, `status`, `receipts`, `evidence`, and
`knowledge-status` are the read commands planned for the TUI adapter.

## 4. Run lifecycle

### Create

`create` requires a bounded objective, an authorized workspace, and the exact
repository revision being worked on:

```powershell
$revision = git rev-parse HEAD
uv run --locked vesper-agent create `
  --objective "Inspect the bounded task" `
  --workspace . `
  --repository-revision $revision `
  --acceptance-check git-diff-check
```

Use a disposable standalone clone for work that needs the repository root.
The repository-root workspace flag is an additional explicit OpenCode gate:

```powershell
uv run --locked vesper-agent `
  --runtime opencode `
  --model provider/model `
  --allow-repository-root-workspace `
  create --objective "Bounded task" --workspace . `
  --repository-revision $revision
```

Do not treat a successful offline run as permission for broker, account,
provider, trading, live deployment, model promotion, or protected-data work.

### Inspect or resume

```powershell
uv run --locked vesper-agent status <run-id>
uv run --locked vesper-agent resume <run-id>
```

Resume uses the run's persisted checkpoint and knowledge snapshot. It does not
silently replace historical context with the current vault.

### Approval, rejection, and cancellation

These commands change persisted run state and require deliberate operator use:

```powershell
uv run --locked vesper-agent approve <run-id> `
  --checkpoint-id <checkpoint-id> `
  --operator-id <operator-id> `
  --reason "Reviewed the current checkpoint"

uv run --locked vesper-agent reject <run-id> `
  --checkpoint-id <checkpoint-id> `
  --operator-id <operator-id> `
  --reason "Does not meet the acceptance boundary"

uv run --locked vesper-agent cancel <run-id> `
  --reason "Operator cancellation"
```

An approval is bound to the checkpoint shown. Re-check status, receipts, and
evidence before approving a changed checkpoint.

## 5. Agent work commands

The agent path is bounded and serialized through the configured Qwen route. It
does not create a scheduler.

```powershell
uv run --locked vesper-agent agent-roster

uv run --locked vesper-agent agent-enqueue `
  --role v20-development `
  --session-id <session-id> `
  --objective "Review the bounded change" `
  --priority 50

uv run --locked vesper-agent agent-queue

uv run --locked vesper-agent agent-run-next `
  --worker-id <worker-id> `
  --repository-revision $revision `
  --prior-session-date YYYY-MM-DD `
  --evidence-json '{}'
```

For a direct single-agent run, use `agent-run` with `--role`, `--session-id`,
`--objective`, `--repository-revision`, `--prior-session-date`, and optional
`--evidence-json`. The evidence value must be a JSON object.

Daily review commands:

```powershell
uv run --locked vesper-agent agent-digest YYYY-MM-DD
uv run --locked vesper-agent agent-review YYYY-MM-DD <operator-id>
uv run --locked vesper-agent agent-gate YYYY-MM-DD
```

## 6. Use the Obsidian vault

`knowledge/` is the repository-owned Obsidian-compatible vault. Obsidian is
optional; the runtime reads Markdown directly.

1. Draft or edit a note under `knowledge/inbox/`.
2. Keep `vesper_status: candidate` while it is under review.
3. Do not include credentials, secrets, raw market data, temporary task state,
   or unsupported authority claims.
4. After explicit human review, set `vesper_status: approved` and move a
   reusable procedure to `knowledge/skills/` or durable memory to
   `knowledge/memory/`.
5. Synchronize and inspect the derived index:

```powershell
uv run --locked vesper-agent knowledge-sync
uv run --locked vesper-agent knowledge-status
uv run --locked vesper-agent knowledge-search `
  --query "split adjustment validation" `
  --role v20-development
```

The controller ignores drafts in `inbox/`. Synchronization fails closed for
invalid approved frontmatter, duplicate IDs, kind/directory mismatches,
symlinked vault paths, or invalid UTF-8.

## 7. TUI status and planned use

There is no runnable TUI binary or TUI package in the current checkout. The
`TUI testing/` directory contains design and implementation-plan files only.
Do not run planned build or launch commands as though they are current.

The approved read-only bakeoff design describes a future TUI that calls only
these fixed JSON commands:

```text
active
approvals
knowledge-status
status <run-id>
receipts <run-id>
evidence <run-id>
```

Its planned screens are Overview, Runs, and Approvals. Planned keys are:

```text
1 / 2 / 3  switch screen
r          refresh
space      pause or restart refresh
/          filter
t          theme
?          help
q          quit
```

A broader Ratatui operations-console design also exists, but implementation has
not started. Its proposed ten-screen layout and control actions are design
material, not available controls. Any future TUI must remain read-only until
the Python controller, permissions, freshness checks, and explicit confirmation
gates are implemented and verified.

## 8. Troubleshooting

- **Command not found:** run from the repository root with
  `uv run --locked vesper-agent ...`.
- **`platform unavailable`:** inspect the configured state, evidence, profile,
  research-data, and knowledge paths. The CLI exits with code `4` for this
  controller-unavailable boundary.
- **Knowledge search is missing a recent note:** run `knowledge-sync` first.
  Only approved notes visible to the selected role are returned.
- **JSON consumer fails:** add `--json` before the command and keep human-only
  output out of the parser.
- **TUI launch instructions are missing:** the TUI is not implemented in this
  checkout; use the CLI read commands above.

## Source of truth

For current behavior, check `vesper/platform/cli.py`, `knowledge/README.md`,
`docs/runbooks/obsidian-knowledge.md`, and the files under `TUI testing/`.
Repository instructions, policy, tests, typed evidence, approval gates, and
current controller state always outrank this guide.
