# Obsidian + LangGraph Knowledge Standard

- Status: Accepted
- Date: 2026-07-28
- Owner: V20 operator
- Scope: Local agent knowledge, memories, and verified procedures

## Goal

Make a dedicated, repository-local Obsidian vault the human-readable source of
truth for V20 knowledge while LangGraph Store supplies controller-owned runtime
persistence, scoped retrieval, and immutable per-run context snapshots.

## Decisions

1. `knowledge/` is the dedicated V20 Obsidian vault. It is ordinary Markdown,
   remains usable without Obsidian, and is versioned with the repository.
2. The legacy external vault is not read, migrated, renamed, or modified.
3. Only approved notes under `knowledge/memory/` and `knowledge/skills/` enter
   runtime knowledge. Notes in `knowledge/inbox/`, templates, and ordinary vault
   documentation are never injected.
4. LangGraph Store contains a rebuildable copy of approved documents and a
   controller-created snapshot for each run. Obsidian Markdown remains canonical.
5. SQLite FTS5 is the initial local retrieval index. A vector index is not added
   until a local, no-network embedding implementation beats FTS5 in a V20-specific
   benchmark.
6. Specialists cannot read or write the vault directly. The controller retrieves
   a bounded, role-scoped packet and injects it into the specialist prompt.
7. Existing receipt-derived `MemoryRecord` entries remain a separate authoritative
   runtime boundary. Obsidian knowledge cannot masquerade as validated run evidence.

## Vault contract

An approved note must be UTF-8 Markdown with YAML frontmatter:

```yaml
---
vesper_id: split-adjustment-policy
vesper_kind: memory
vesper_status: approved
vesper_scope: shared
title: Split adjustment policy
tags:
  - prices
  - splits
---
```

`vesper_kind` is `memory` or `skill`. `vesper_scope` is `shared`,
`v20-product`, `v20-development`, or `v20-risk-review`. IDs are stable and
unique across the vault. Approved notes with missing or invalid metadata fail
synchronization. Unapproved notes are ignored.

The stored document includes its relative vault path and SHA-256 of the complete
source file. A path is never accepted through a symbolic link or junction.

## Runtime data flow

```text
knowledge/{memory,skills}/**/*.md
        |
        | deterministic parse + validation + SHA-256
        v
LangGraph Store knowledge documents <----> SQLite FTS5 derived index
        |
        | objective search + role filter + fixed size limit
        v
per-run immutable KnowledgeContext records
        |
        | controller prompt injection
        v
Product / Development / Risk Review
```

At run creation, the controller synchronizes the vault, searches once per role,
and persists the selected documents in the run snapshot namespace. Resume uses
that snapshot and therefore cannot silently change context if the vault changes
mid-run.

The injected packet explicitly states that repository state, policy, typed
evidence, validation, and current task inputs outrank knowledge notes. A retrieved
memory is context, not proof. A retrieved skill is a procedure, not new authority.

## Retrieval

FTS5 indexes title, tags, and body. Results are filtered to `shared` plus the
requesting role before ranking. The controller selects at most five documents and
at most 8,000 characters for a role snapshot. Empty or punctuation-only queries
return no documents.

The FTS database is derived and may be deleted and rebuilt. Store synchronization
is idempotent: changed source hashes update records, missing notes delete records,
and a repeated synchronization produces no changes.

## Operator surface

The existing `vesper-agent` CLI gains:

- `knowledge-sync` to validate and synchronize the configured vault;
- `knowledge-search --query ... --role ...` to inspect scoped retrieval;
- `knowledge-status` to inspect the current synchronized corpus.

The global `--knowledge-root` option defaults to `knowledge`. It must identify a
directory inside the active repository for production run creation.

## Failure behavior

- Missing dedicated vault: fail synchronization and production run creation.
- Duplicate approved ID: fail without partially replacing the previous corpus.
- Malformed approved frontmatter: fail with the relative note path.
- Invalid UTF-8 or source link/junction: fail.
- Store/index interruption: the next synchronization rebuilds the FTS index from
  the successfully parsed source set and repairs Store records idempotently.
- Missing snapshot on a historical run: inject no Obsidian context; never read the
  current vault as an implicit replacement.

## Security and authority

- No network access, hosted service, Obsidian plugin, MCP, or new credential.
- No content under `vesper/data/massive/` or `vesper/data/model_research/` is read
  or copied.
- No secrets may be stored in the vault.
- `knowledge/` joins the controller-protected repository paths.
- Agents may propose notes in an inbox only in a separately authorized workflow;
  this implementation does not add agent-authored vault writes.

## Acceptance criteria

1. Approved memory and skill notes synchronize into LangGraph Store with stable
   IDs, hashes, paths, types, scopes, titles, tags, and content.
2. Candidate/unapproved notes do not enter runtime Store records or prompts.
3. Changed and deleted notes are reconciled, and duplicate IDs fail closed.
4. Scoped FTS retrieval is deterministic and excludes other roles.
5. A production run persists bounded role-specific snapshots and uses them in
   specialist prompts; resumes reuse the snapshot.
6. CLI sync, search, status, and help remain side-effect-safe as documented.
7. The vault is protected from specialist mutation.
8. Focused tests, the full V20 test suite, lint, formatting, compilation, import
   tests, lock verification, and final diff checks pass.

## Alternatives rejected

- External or cloud Obsidian integration: unnecessary and weakens local authority.
- Treating Store as the source of truth: creates drift from inspectable Markdown.
- Automatically promoting conversation summaries: bypasses validation and review.
- Adding LangMem, a cloud vector store, or an embedding-model download: expands
  dependencies and network authority before V20-specific evidence exists.
