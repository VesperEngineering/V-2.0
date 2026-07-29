# Obsidian knowledge operator runbook

## Purpose

Use the repository-local `knowledge/` vault to maintain durable V20 memories and
reviewed procedures. Open that directory as an Obsidian vault if desired, or edit
the Markdown with any text editor.

The canonical copy is always Markdown. `store.sqlite3` and
`knowledge-index.sqlite3` are derived controller state and can be rebuilt.

## Author a note

1. Copy `knowledge/templates/memory.md` or `knowledge/templates/skill.md` into
   `knowledge/inbox/`.
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

## Synchronize and inspect

From the repository root:

```powershell
uv run --locked vesper-agent knowledge-sync
uv run --locked vesper-agent knowledge-status
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
or mutate an external legacy vault as part of recovery. The legacy
`profiles/vesper-factory` bundle is not loaded by the native profile catalog and
is not a source for this vault.
