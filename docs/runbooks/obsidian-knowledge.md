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
4. Keep `vesper_status: candidate` while drafting and set
   `vesper_retention: adaptive` or `pinned`.
5. Remove template guidance, confirm the note contains no secrets, credentials,
   raw market data, temporary task state, or unsupported authority claims.
6. After human review, set `vesper_status: approved` and manually move the note
   to `knowledge/memory/` or `knowledge/skills/`. The directory must agree with
   `vesper_kind`. Only an operator may approve, archive, reactivate, change
   retention, or delete a note.

The controller ignores `inbox/`, `raw/`, `wiki/`, `templates/`, README files,
and any note that is not an admitted active or archived document.

## Observe and review candidates

Submit a durable observation rather than writing lifecycle state directly:

```powershell
uv run --locked vesper-agent knowledge-observe `
  --concept-key brief-writing `
  --title "Prefer brief writing" `
  --kind memory `
  --scope shared `
  --summary "Prefer brief, direct wording unless detail is requested." `
  --source-ref "operator-task-reference" `
  --explicit
```

`--explicit` creates a candidate immediately. Without it, the controller creates
a candidate only after three distinct source references for the same stable
concept key. It never promotes, archives, reactivates, deletes, or moves a file.
Review candidates in Obsidian (or another Markdown editor), then manually apply
the frontmatter status and move them to the correct directory.

## Synchronize and inspect

From the repository root:

```powershell
uv run --locked vesper-agent knowledge-sync
uv run --locked vesper-agent knowledge-status
uv run --locked vesper-agent knowledge-search `
  --query "split adjustment validation" `
  --role v20-development
uv run --locked vesper-agent knowledge-compaction-plan --target-lines 2800
uv run --locked vesper-agent knowledge-reactivation-plan
```

Use the global `--knowledge-root <path>` option before the command only when
operating on an approved repository-local vault at a non-default path. Production
run creation rejects a vault outside the approved clone.

`knowledge-sync` validates the complete approved corpus before changing derived
state, reconciles additions, updates, and deletions in LangGraph Store, then
rebuilds the FTS5 index. An invalid approved note, duplicate ID, kind/directory
mismatch, symlinked vault, or invalid UTF-8 fails closed.

The active `memory/` and `skills/` corpus cannot exceed 3,000 complete Markdown
source lines. The count includes frontmatter and Markdown content of active notes;
archived notes do not consume it. `knowledge-sync` enforces this limit before it
changes derived state. The two planning commands only return deterministic review
proposals. Apply an approved compaction or reactivation manually in Obsidian by
moving the file and setting the matching status and retention.

`knowledge-search` returns only `shared` documents and documents scoped to the
selected role. Synchronize before using it after Markdown changes.

## Run behavior

Production `create` performs a sync and creates one bounded knowledge snapshot
per specialist role before executing Product. Runtime metadata records the
resolved vault path and sync counts. The vault is a protected controller path.

Changing or deleting a note after run creation does not alter that run. A resume
uses its persisted snapshot. Create a new run to use the revised corpus.

Search and run snapshots can temporarily include archived notes, but no more than
two archived documents may be selected within the existing five-document,
8,000-character context limits. Temporary retrieval changes neither canonical
file location nor status, retention, authority, or the active line budget.

Selected notes receive usage credit only after the run is accepted. Selection,
failed runs, and unaccepted runs do not count as successful use.

## Update, archive, or delete

- To revise a note, edit its canonical Markdown without changing `vesper_id`,
  review it again, and synchronize.
- To archive an adaptive note, manually move it from `memory/` or `skills/` to
  the matching `archive/memory/` or `archive/skills/` directory, set
  `vesper_status: archived`, retain `vesper_retention: adaptive`, then
  synchronize. Archived notes remain searchable and may be retrieved temporarily.
- To reactivate an archived note permanently, obtain operator review, manually
  move it to the matching active directory, set `vesper_status: approved`, and
  synchronize only if it fits the active 3,000-line budget.
- To delete a note, an operator removes its canonical Markdown and synchronizes.
  There is no controller delete command. Existing run snapshots remain unchanged.
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
