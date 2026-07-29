# Obsidian and LangGraph Knowledge Standard Receipt

- Recorded: 2026-07-28
- Environment: Python 3.11, uv, Windows
- Result: repository-local knowledge standard implemented and verified

## Delivered

- `knowledge/` is the dedicated Obsidian-compatible Markdown vault and the
  canonical source for operator-approved memories and procedures.
- Strict frontmatter admission supports stable IDs, memory/skill kinds, shared
  or role-specific scopes, titles, tags, source paths, and source SHA-256.
- LangGraph Store holds a rebuildable typed copy and immutable per-run role
  snapshots. A separate SQLite FTS5 database supplies local lexical retrieval.
- Synchronization is idempotent and reconciles added, changed, and deleted
  notes. Invalid UTF-8, malformed approved notes, duplicate IDs, kind/directory
  mismatches, linked notes, missing vaults, and external vault roots fail closed.
- Product, Development, and Risk Review receive at most five documents and 8,000
  body characters from their exact run snapshot. Prompt boundary characters in
  note content are escaped, and injected knowledge is explicitly non-authoritative.
- `knowledge/` is controller-protected. Specialists have no direct vault access.
- The CLI exposes global `--knowledge-root` plus `knowledge-sync`,
  `knowledge-search`, and `knowledge-status`.
- ADR-0002, the operator runbook, root README, ADR-0001, agent handoff guidance,
  vault templates, and vault-local guidance describe the same implemented
  contract.

## Authority and migration boundary

No dependency, network call, MCP server, Obsidian plugin, hosted service,
credential, trading setting, risk limit, model, schedule, or protected data was
added or changed. The legacy external vault and the legacy
`profiles/vesper-factory` bundle were neither read for ingestion nor modified;
the native profile loader already excludes that bundle.

Receipt-derived `MemoryRecord` entries remain separate validated runtime records.
Operator-authored Markdown is context and cannot become evidence, permission, or
approval merely by being retrieved.

## Test-first evidence

The implementation used focused red/green cycles for the parser, Store/FTS
synchronization, snapshots, prompt injection, production service integration,
CLI routing, prompt-boundary escaping, and repository-local vault enforcement.
Representative observed red states included missing knowledge contracts/module,
missing synchronization and snapshot APIs, missing composition callback, missing
CLI commands, a literal closing prompt boundary, and acceptance of an external
operator vault. Each corresponding focused test was then observed green.

## Fresh verification

```text
Focused knowledge tests:
  16 passed in 1.40s

Complete V20 suite:
  657 passed, 5 skipped in 86.33s

Isolated first-party import suite:
  65 passed in 25.94s

Changed-file Ruff format check:
  11 files already formatted

Repository Ruff lint:
  All checks passed!

Modified-file py_compile:
  success, no output

First-party compileall:
  success, no output

Dependency verification:
  uv lock --check: 79 packages resolved
  uv pip check: 78 packages checked; all compatible

Final scope/documentation checks:
  git diff --check: success
  trailing whitespace across implementation files: none
  documented local links and CLI tokens: present
  CodeGraph: synchronized 23 changed files
```

The real CLI smoke test used the repository vault and isolated local state. It
observed a successful empty-corpus sync, zero memory/skill documents in status,
and an empty scoped search result. This is the expected initial condition: no
note is admitted until an operator approves it.

The optional machine-readable guideline verifier could not execute repository
commands because `AGENTS.md` has no `codex-guidelines` fenced block. The explicit
manual format, lint, test, compilation, import, dependency, and diff gates from
`AGENTS.md` were used instead.

## Residual risks and next gate

- Retrieval is lexical FTS5. Add embeddings or vector search only after a local
  V20 benchmark demonstrates better retrieval quality without expanding network
  or credential authority.
- SQLite remains a single-host persistence boundary; normal backup, migration,
  and corruption-recovery discipline still applies to historical run snapshots.
- Existing historical runs without a `KnowledgeContext` snapshot receive no
  current-vault fallback by design.
- The approved corpus starts empty. The next operator action is to review a
  candidate note in `knowledge/inbox/`, promote it with a stable ID and approved
  frontmatter, then run `knowledge-sync` and inspect it with `knowledge-search`.

The two pre-existing untracked research reports were preserved untouched and are
not part of this implementation.
