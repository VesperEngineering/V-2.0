# Task 8 implementer report

## Documentation commit

- SHA: `9ab7b68`
- Message: `docs(knowledge): document adaptive core operations`

## Files and reason

- `AGENTS.md` and `README.md`: document observation-only agent behavior and the
  governed CLI lifecycle.
- `knowledge/README.md` and `knowledge/inbox/README.md`: define active versus
  archive status, candidate review, manual movement, and lifecycle authority.
- `knowledge/archive/README.md`, `knowledge/archive/memory/README.md`,
  `knowledge/archive/skills/README.md`, `knowledge/raw/README.md`, and
  `knowledge/wiki/README.md`: establish the non-admitted vault structure without
  adding knowledge notes.
- `docs/adr/ADR-0003-adaptive-knowledge-core.md`: records the accepted extension
  to ADR-0002 and its exact lifecycle, budget, retrieval, and local-only choices.
- `docs/runbooks/obsidian-knowledge.md`: provides operator commands, review,
  archive, reactivation, budget, retrieval, and recovery guidance.

## Verification

- `rg -n "3,000|knowledge-observe|knowledge-compaction-plan|knowledge-reactivation-plan|vesper_status: archived" README.md AGENTS.md knowledge docs/adr docs/runbooks`
- `uv run --locked vesper-agent --help`
- `uv run --locked vesper-agent knowledge-observe --help`
- `uv run --locked vesper-agent knowledge-compaction-plan --help`
- `uv run --locked vesper-agent knowledge-reactivation-plan --help`
- Relative Markdown link/path check over every changed documentation file.
- `git diff --check` and `git diff --cached --check`.

## Self-review

The change is documentation-only and contains no approved knowledge notes. CLI
examples use the implemented command names and required options. The text keeps
approval, archival, permanent reactivation, retention changes, deletion, and file
movement operator-only; planning and retrieval are explicitly non-mutating.
