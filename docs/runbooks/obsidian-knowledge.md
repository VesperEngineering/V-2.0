# Obsidian knowledge operator runbook

## Purpose

Use the repository-local `knowledge/` vault to maintain durable V20 memories and
reviewed procedures. Open that directory as an Obsidian vault if desired, or edit
the Markdown with any text editor.

The canonical copy is always Markdown. `store.sqlite3` and
`knowledge-index.sqlite3` are derived controller state and can be rebuilt.

## Author a note

1. Copy `knowledge/templates/v20-core-memory.md` into `knowledge/inbox/`.
2. Give it a stable unique `vesper_id`. Do not reuse an ID for a different idea.
3. Choose exactly one scope:
   - `shared`
   - `v20-product`
   - `v20-development`
   - `v20-risk-review`
4. Keep `vesper_status: candidate` while drafting.
5. Remove template guidance, confirm the note contains no secrets, credentials,
   raw market data, temporary task state, or unsupported authority claims.
6. After human review, set `vesper_status: approved` and move the note to
   `knowledge/memory/` or `knowledge/skills/`. The directory must agree with
   `vesper_kind`.

The controller ignores `inbox/`, `templates/`, README files, and any note that is
not explicitly approved.

## Dream Gate

Dream Gate reads redacted notes from `knowledge/sessions/`, writes an immutable
report to `knowledge/dreams/reports/`, and automatically consolidates stable
memory and procedure learnings into `knowledge/memory/` or `knowledge/skills/`.
Applied changes include source-session and dream receipts in the report.

The vault is visible in Obsidian immediately. Dream memory supplies context; it
does not grant broker, credential, protected-data, scheduler, risk, trading,
deletion, or deployment authority.

Use `knowledge/memory/v20-core/` for active shared memory and
`knowledge/skills/v20/` for active shared procedures. Both remain inside the
normal approved scanner roots.

## Synchronize and inspect

From the repository root:

```powershell
uv run --locked vesper-agent knowledge-sync
uv run --locked vesper-agent knowledge-status
uv run --locked vesper-agent knowledge-budget
uv run --locked vesper-agent knowledge-search `
  --query "split adjustment validation" `
  --role v20-development
```

Use the global `--knowledge-root <path>` option before the command only when
operating on an approved repository-local vault at a non-default path. Production
run creation rejects a vault outside the approved clone.

`knowledge-sync` validates the complete approved corpus before changing derived
state, reconciles additions, updates, and deletions in LangGraph Store, then
rebuilds the FTS5 index. An invalid approved note, duplicate ID, kind/directory
mismatch, symlinked vault, or invalid UTF-8 fails closed.

`knowledge-search` returns only `shared` documents and documents scoped to the
selected role. Synchronize before using it after Markdown changes.

`knowledge-budget` reports the 3,000-source-line active limit and non-binding
compaction candidates. It never moves or deletes notes.

## Working memory and dreaming

`memory-status --agent-id <role>` reports one agent's 2,000-word working-memory
core. Validated controller receipts may submit candidates; `memory-curate` can
curate explicitly supplied candidates. The controller writes the core,
archive, and reversible history under `knowledge/working-memory/`.

`dream-run` performs one Qwen Dream Gate pass. It reads redacted
`knowledge/sessions/` notes and approved active knowledge, writes a JSON report
under `knowledge/dreams/reports/`, and applies ordinary memory/procedure
learnings. Chat also runs this pass automatically when a session closes. No
scheduler is enabled.

V20-routed agent events are appended to `knowledge/sessions/` automatically.
User instructions, assistant messages, controller-mediated tool calls/results,
and exposed runtime events are redacted at capture. Use `vesper-agent
session-status` to confirm the number of captured sessions and events before
running `dream-run`. A session file is evidence that capture worked;
`source_session_ids` in the Dream Gate report shows what the dream read.
The external Codex desktop conversation is not available to V20 and is not
captured.

## Run behavior

Production `create` performs a sync and creates one bounded knowledge snapshot
per specialist role before executing Product. Runtime metadata records the
resolved vault path and sync counts. The vault is a protected controller path.

Changing or deleting a note after run creation does not alter that run. A resume
uses its persisted snapshot. Create a new run to use the revised corpus.

## Update or delete

- To revise a note, edit its canonical Markdown without changing `vesper_id`,
  review it again, and synchronize.
- To retire a note, delete or move it out of `memory/` or `skills/`, then
  synchronize. Existing run snapshots remain unchanged.
- To change the meaning substantially, retire the old ID and create a new one so
  provenance remains clear in Git history.

## Recovery

If the derived knowledge index is missing or suspected stale, run
`knowledge-sync`; it is rebuilt from approved Markdown. If controller state is
being restored, restore the normal platform SQLite backup for historical run
snapshots, then synchronize the current vault for future runs.

Never treat a derived database as the only backup of V20 knowledge. Do not import
or mutate an external legacy vault or retired agent-profile bundle during recovery.
Only `profiles/native/` and this repository-owned vault belong to the native platform.
