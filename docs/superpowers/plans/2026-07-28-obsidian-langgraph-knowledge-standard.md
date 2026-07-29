# Obsidian + LangGraph Knowledge Standard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repository-local `knowledge/` Obsidian vault the canonical source for approved V20 memories and skills, with scoped persistence and retrieval through LangGraph Store.

**Architecture:** A deterministic parser validates approved Markdown notes, stores typed derived records in LangGraph Store, and rebuilds a local SQLite FTS5 index. Run creation snapshots bounded role-specific results so specialist context is stable across resume.

**Tech Stack:** Python 3.11, Pydantic 2, PyYAML, LangGraph Store, SQLite FTS5, Typer, pytest.

## Global Constraints

- Do not modify `config/settings.yaml`, trading parameters, risk limits, models, schedules, or protected data.
- Do not read from or write to the legacy external Obsidian vault.
- Add no dependency, network call, hosted service, credential, MCP, or model download.
- Follow test-first red/green cycles for every runtime behavior.
- Keep Obsidian content read-only to the controller and unavailable as a specialist filesystem path.
- Preserve unrelated untracked reports and do not stage or commit them.

---

### Task 1: Typed knowledge documents and Markdown parsing

**Files:**
- Create: `vesper/platform/knowledge.py`
- Modify: `vesper/platform/contracts.py`
- Create: `tests/platform/test_knowledge.py`

**Interfaces:**
- Produces: `KnowledgeKind`, `KnowledgeScope`, `KnowledgeDocument`,
  `KnowledgeContext`, `KnowledgeSyncError`, and
  `load_approved_documents(vault_root: Path) -> tuple[KnowledgeDocument, ...]`.

- [ ] **Step 1: Write failing parser tests**

Cover an approved memory, an approved skill, an unapproved inbox note, malformed
approved metadata, duplicate IDs, UTF-8 failure, and a linked source path. Assert
the exact relative path and SHA-256 stored in each `KnowledgeDocument`.

- [ ] **Step 2: Verify the parser tests fail because the contracts and loader do not exist**

Run:

```powershell
uv run --locked python -m pytest tests/platform/test_knowledge.py -q
```

- [ ] **Step 3: Implement the minimal typed parser**

Add strict enums and Pydantic models to `contracts.py`. In `knowledge.py`, scan
only `memory/**/*.md` and `skills/**/*.md`, parse a leading YAML document between
`---` markers, require the accepted frontmatter fields, reject links, normalize
relative paths to POSIX form, and sort by `knowledge_id`.

- [ ] **Step 4: Run the parser tests to green**

Run the focused command from Step 2 and keep all errors path-specific.

### Task 2: LangGraph Store synchronization and FTS5 retrieval

**Files:**
- Modify: `vesper/platform/knowledge.py`
- Modify: `vesper/platform/persistence.py`
- Modify: `tests/platform/test_knowledge.py`
- Modify: `tests/platform/test_persistence.py`

**Interfaces:**
- Consumes: `KnowledgeDocument` and `LangGraphStoreAdapter`.
- Produces: `SqliteKnowledgeIndex`, `ObsidianKnowledgeService.sync()`,
  `ObsidianKnowledgeService.search(role, query)`, and Store deletion support.

- [ ] **Step 1: Write failing synchronization and retrieval tests**

Prove first sync adds records; replay is unchanged; changed hashes update; removed
files delete; duplicate IDs leave the previous Store corpus intact; shared notes
are visible to every role; role notes never cross scopes; punctuation-only queries
return nothing; and close/reopen preserves searchable records.

- [ ] **Step 2: Verify the new tests fail for the missing synchronization behavior**

```powershell
uv run --locked python -m pytest tests/platform/test_knowledge.py tests/platform/test_persistence.py -q
```

- [ ] **Step 3: Implement minimal Store and FTS5 behavior**

Extend `LangGraphStoreAdapter` with `delete`. Add `knowledge_index_db` to
`PlatformPaths`, create the FTS5 index in `open_persistence`, and close it with
the other persistence resources. Synchronization parses the complete source set
before any mutation, reconciles Store keys by stable ID, and rebuilds the FTS
table in one SQLite transaction.

- [ ] **Step 4: Run focused persistence tests to green**

Run the Step 2 command and confirm the existing concurrent Store test remains
green.

### Task 3: Immutable per-run knowledge snapshots

**Files:**
- Modify: `vesper/platform/knowledge.py`
- Modify: `tests/platform/test_knowledge.py`

**Interfaces:**
- Produces:
  `snapshot(task: TaskRequest) -> tuple[KnowledgeContext, ...]` and
  `context(run_id: str, role: SpecialistRole) -> KnowledgeContext | None`.

- [ ] **Step 1: Write failing snapshot tests**

Assert one context per role, no more than five documents or 8,000 body characters,
current run/task/revision binding, role filtering, deterministic order, and
unchanged snapshots after the source documents are later resynchronized.

- [ ] **Step 2: Verify the snapshot tests fail for missing APIs**

```powershell
uv run --locked python -m pytest tests/platform/test_knowledge.py -q
```

- [ ] **Step 3: Implement snapshots in the run namespace**

Search using the task objective, store each typed `KnowledgeContext` under
`("runs", run_id, "knowledge")`, and make `context` read only that namespace.

- [ ] **Step 4: Run snapshot tests to green**

Run the Step 2 command.

### Task 4: Specialist context and controller protection

**Files:**
- Modify: `vesper/platform/composition.py`
- Modify: `vesper/platform/service.py`
- Modify: `tests/platform/test_composition.py`
- Modify: `tests/platform/test_service.py`
- Modify: `tests/platform/test_authority_boundaries.py`

**Interfaces:**
- Consumes: `ObsidianKnowledgeService.context(run_id, role)`.
- Produces: bounded `<v20_knowledge>` prompt context and automatic create-time
  synchronization/snapshotting.

- [ ] **Step 1: Write failing composition/service tests**

Assert approved knowledge appears in the correct role prompt with path/hash
provenance and the non-authority warning; foreign-role notes do not appear; no
snapshot produces no section; create synchronizes and snapshots before graph
start; resume uses stored context; and `knowledge/` is a protected workspace path.

- [ ] **Step 2: Verify tests fail for missing integration**

```powershell
uv run --locked python -m pytest tests/platform/test_composition.py tests/platform/test_service.py tests/platform/test_authority_boundaries.py -q
```

- [ ] **Step 3: Implement controller-owned integration**

Add a context-reader callback to `NativeSpecialistComposition`; render only the
typed snapshot in the prompt. Give `LocalPlatformService` a repository-relative
knowledge root, synchronize/snapshot during `_create_run_locked`, persist the
path in run-runtime metadata, and include `knowledge` in protected root paths.

- [ ] **Step 4: Run integration tests to green**

Run the Step 2 command.

### Task 5: CLI standard and operator inspection

**Files:**
- Modify: `vesper/platform/cli.py`
- Modify: `vesper/platform/service.py`
- Modify: `tests/platform/test_cli.py`
- Modify: `tests/platform/test_service.py`

**Interfaces:**
- Produces: global `--knowledge-root`, `knowledge-sync`, `knowledge-search`, and
  `knowledge-status` commands.

- [ ] **Step 1: Write failing CLI routing and side-effect tests**

Assert the default root is `knowledge`; explicit roots reach the service; role
values are validated; commands emit JSON-compatible results; and `--help` still
constructs neither persistence nor service.

- [ ] **Step 2: Verify CLI tests fail for the missing commands**

```powershell
uv run --locked python -m pytest tests/platform/test_cli.py tests/platform/test_cli_help_isolation.py -q
```

- [ ] **Step 3: Implement the minimal CLI/service operations**

Extend `CliConfig` and `PlatformService`; route sync/search/status to the knowledge
service opened through existing local persistence. Do not add any vault write
command.

- [ ] **Step 4: Run CLI tests to green**

Run the Step 2 command.

### Task 6: Dedicated V20 vault and synchronized documentation

**Files:**
- Create: `knowledge/README.md`
- Create: `knowledge/memory/README.md`
- Create: `knowledge/skills/README.md`
- Create: `knowledge/inbox/README.md`
- Create: `knowledge/templates/memory.md`
- Create: `knowledge/templates/skill.md`
- Create: `docs/adr/ADR-0002-obsidian-langgraph-knowledge.md`
- Create: `docs/runbooks/obsidian-knowledge.md`
- Modify: `README.md`
- Modify: `docs/adr/ADR-0001-native-langgraph-platform.md`

**Interfaces:**
- Produces: copyable note templates, vault operating rules, CLI runbook, migration
  boundary, and architecture cross-links.

- [ ] **Step 1: Add the vault starter files and templates**

Document approval state, scopes, stable IDs, secret/data prohibitions, inbox
behavior, and the fact that opening `knowledge/` in Obsidian is optional.

- [ ] **Step 2: Add ADR-0002 and update architecture references**

Record Markdown as canonical, Store/FTS as derived, per-run snapshots, and the
rejected external/cloud alternatives. Leave historical receipts unchanged.

- [ ] **Step 3: Add a runnable operator runbook and README commands**

Commands must match actual CLI help and use `uv run --locked vesper-agent`.

- [ ] **Step 4: Check documentation paths, flags, and examples against code**

Use `rg` to verify every documented option and command exists in `cli.py`.

### Task 7: Verification and receipt

**Files:**
- Create: `docs/receipts/obsidian-langgraph-knowledge-standard-receipt.md`

**Interfaces:**
- Produces: fresh verification evidence and scope reconciliation.

- [ ] **Step 1: Format and check modified Python paths**

```powershell
uv run --locked ruff format vesper/platform/knowledge.py vesper/platform/contracts.py vesper/platform/persistence.py vesper/platform/composition.py vesper/platform/service.py vesper/platform/cli.py tests/platform/test_knowledge.py tests/platform/test_persistence.py tests/platform/test_composition.py tests/platform/test_service.py tests/platform/test_authority_boundaries.py tests/platform/test_cli.py
uv run --locked ruff check vesper scripts tests
```

- [ ] **Step 2: Run focused then complete tests**

```powershell
$testRoot = Join-Path $env:LOCALAPPDATA "Temp\v20-obsidian-pytest-$PID"
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
uv run --locked python -m pytest tests/platform -q --basetemp (Join-Path $testRoot "platform")
uv run --locked python -m pytest tests -q --basetemp (Join-Path $testRoot "all")
```

- [ ] **Step 3: Compile, import-check, and verify dependency lock**

```powershell
$compileRoot = Join-Path $env:LOCALAPPDATA "Temp\v20-obsidian-compile-$PID"
$env:PYTHONPYCACHEPREFIX = Join-Path $compileRoot "pycache"
uv run --locked python -m compileall -q vesper scripts tests
uv run --locked python -m pytest tests/test_imports.py -q --basetemp (Join-Path $testRoot "imports")
uv lock --check
```

- [ ] **Step 4: Inspect scope and record exact results**

Run `git diff --check`, inspect `git diff --stat` and the complete diff, confirm
the two unrelated untracked reports remain untouched, and write the exact command
results and residual risks into the new receipt.
