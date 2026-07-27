# Native Agent Platform Offline Vertical Slice Implementation Plan

> Implementation status note (2026-07-27): the operator approved `langsmith` solely as an inert
> transitive dependency of LangGraph/`langchain-core`. Local SQLite checkpoint/Store persistence,
> the bounded Product/Development/Validation/Risk graph, persisted human approval, recovery, and
> graph-backed lifecycle commands are implemented. Tracing and CLI analytics are forced off, and a
> fresh-process deny-egress test covers the complete local graph path. The original host Codex SDK
> gateway is superseded for new runtime work by a fake-tested Docker Sandboxes Codex adapter.
> Read-only and workspace-write Docker canaries passed in a disposable standalone clone; the latter
> uses Codex's externally-sandboxed mode. Mount inspection subsequently found Docker's default
> read-write shared skills store, so the canary is not accepted as a production isolation boundary.
> The adapter now rejects shared or additional host mounts; activation requires a replacement
> sandbox created with skills sharing disabled. The operator selected one-shot lifecycle: every
> specialist turn receives a fresh uniquely named sandbox that is force-removed after its outcome.
> OpenCode remains deferred until a provider API key is available through the sandbox credential
> proxy. LangMem remains deliberately
> deferred because its provider-heavy dependency closure has not been approved. See
> `docs/receipts/M1-dependency-receipt.md`.
> Task 4 below records the completed direct-Codex baseline; ADR-0001,
> `vesper.platform.codex_sandbox`, and `vesper.platform.opencode` govern new model-runtime work.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build V20's first local, resumable Product → Development → deterministic validation → Risk Review → operator approval workflow without invoking a real model, provider, broker, or trading path.

**Architecture:** New code lives in a focused `vesper.platform` package. Pydantic contracts are the serialization boundary, LangGraph owns deterministic routing and interrupts, SQLite owns checkpoints and long-term Store records, and immutable artifacts remain in a content-addressed filesystem evidence store. Model execution and memory consolidation are dependency-injected ports tested with deterministic fakes; real provider execution remains opt-in.

**Tech Stack:** Python 3.11, Pydantic 2, LangGraph, `langgraph-checkpoint-sqlite`, Docker Sandboxes with Codex, deferred OpenCode, Typer, PyYAML, pytest, Ruff, SQLite.

## Global Constraints

- Preserve all uncommitted work and historical evidence.
- Do not connect to Massive, Alpaca, brokers, OpenAI runtime services, or any other external runtime service.
- Do not load credentials, place orders, train or promote models, enable schedules, deploy, commit, push, merge, or rewrite history.
- Do not add full LangChain, hosted databases, tracing, or cloud deployment dependencies. LangSmith
  is accepted only as an inert transitive package and is not a V20 platform service.
- Use deterministic fakes in normal tests; the real Codex integration test is opt-in and skipped by default.
- A specialist response is never acceptance. Deterministic validation, independent Risk Review, and explicit operator approval are authoritative.
- The combined automatic correction budget is three failed validation or risk-review attempts.

---

### Task 1: Dependency Compatibility and Receipt

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `docs/receipts/M1-dependency-receipt.md`
- Create: `tests/platform/test_dependencies.py`

**Interfaces:**
- Consumes: the M0 Python 3.11 `uv` project.
- Produces: importable `langgraph`, `langgraph.checkpoint.sqlite`, `langgraph.store.sqlite`, `openai_codex`, `pydantic`, and `typer` packages.

- [ ] Add an import smoke test that uses `importlib.metadata.version()` and imports only public package boundaries.
- [ ] Run the test and confirm it fails because the new dependencies are absent.
- [ ] Add bounded compatible dependencies, refresh `uv.lock`, and inspect every direct/transitive change.
- [ ] Record versions, licenses, security findings, commands, and the LangMem/full-LangChain conflict in the receipt.
- [ ] Run the smoke test, `uv lock --check`, `uv pip check`, and the complete M0 suite.

### Task 2: Typed Authority Contracts

**Files:**
- Create: `vesper/platform/__init__.py`
- Create: `vesper/platform/contracts.py`
- Create: `tests/platform/test_contracts.py`

**Interfaces:**
- Produces: `TaskRequest`, `SpecialistInput`, `SpecialistReceipt`, `PlatformState`, `ValidationResult`, `RiskReviewDecision`, `CorrectionAttempt`, `ApprovalRequest`, `ApprovalDecision`, `CodexExecutionReceipt`, `MemoryCandidate`, `MemoryRecord`, `EvidenceArtifact`, and `RunMetadata`.
- Every model includes `schema_version`; run-bearing models include `run_id`, `task_id`, `repository_revision`, and UTC timestamps.

- [ ] Write tests for JSON round trips, UTC enforcement, forbidden extra fields, invalid decisions, secret-shaped fields, and acceptance authority.
- [ ] Run the tests and confirm missing contracts fail.
- [ ] Implement the smallest frozen or assignment-validated Pydantic models and enums needed by the tests.
- [ ] Run focused and complete suites.

### Task 3: SQLite Persistence and Evidence

**Files:**
- Create: `vesper/platform/persistence.py`
- Create: `vesper/platform/evidence.py`
- Create: `tests/platform/test_persistence.py`
- Create: `tests/platform/test_evidence.py`

**Interfaces:**
- `open_checkpointer(path: Path) -> ContextManager[SqliteSaver]`
- `open_store(path: Path) -> ContextManager[SqliteStore]`
- `EvidenceStore(root: Path).write(run_id, relative_path, payload) -> EvidenceArtifact`
- `EvidenceStore.verify(artifact) -> bool`
- `EvidenceStore.write_manifest(metadata, artifacts) -> EvidenceArtifact`

- [ ] Write tests for checkpoint reopen/recovery, Store process reopen, namespace isolation, evidence hashes, path traversal rejection, atomic duplicate writes, manifest verification, and corrupt artifact rejection.
- [ ] Run the tests and confirm missing implementations fail.
- [ ] Implement SQLite factories with explicit setup and a content-addressed, atomic filesystem evidence store.
- [ ] Run focused and complete suites.

### Task 4: Codex Port and SDK Adapter

**Files:**
- Create: `vesper/platform/codex.py`
- Create: `tests/platform/test_codex.py`
- Create: `tests/platform/test_codex_integration.py`
- Modify: `pyproject.toml` to register the `local_codex` marker.

**Interfaces:**
- `CodexRequest` is the explicit model, cwd, sandbox, prompt, permissions, timeout, and optional thread ID input.
- `CodexAdapter.start(request) -> CodexExecutionReceipt`
- `CodexAdapter.resume(request) -> CodexExecutionReceipt`
- `FakeCodexAdapter` returns queued deterministic receipts without filesystem or network access.

- [ ] Write tests for start/resume, sandbox mapping, approved-model enforcement, permissions, stream/final capture, timeout, cancellation, usage limits, and non-acceptance.
- [ ] Run tests and confirm the adapter is missing.
- [ ] Implement a narrow wrapper over public `openai_codex` APIs without instantiating the SDK at import time.
- [ ] Add an integration test guarded by both the `local_codex` marker and an explicit opt-in environment flag; verify it skips normally.
- [ ] Run focused and complete suites without authentication.

### Task 5: Native Profiles and Memory Policy

**Files:**
- Create: `profiles/v20-product/SOUL.md`
- Create: `profiles/v20-product/profile.yaml`
- Create: `profiles/v20-development/SOUL.md`
- Create: `profiles/v20-development/profile.yaml`
- Create: `profiles/v20-risk-review/SOUL.md`
- Create: `profiles/v20-risk-review/profile.yaml`
- Create: `vesper/platform/profiles.py`
- Create: `vesper/platform/memory.py`
- Create: `tests/platform/test_profiles.py`
- Create: `tests/platform/test_memory.py`

**Interfaces:**
- `load_profile(name, root) -> SpecialistProfile`
- `MemoryRepository(store).put(actor, candidate) -> MemoryRecord`
- `MemoryRepository.search(actor, namespace) -> list[MemoryRecord]`
- `MemoryConsolidator(adapter).consolidate(input) -> list[MemoryCandidate]`

- [ ] Write tests for complete profile schemas, no stale repository state, prohibited actions, namespace ownership, Risk memory denial, validated-only writes, contradiction/supersession, protected-policy immutability, and structured fake consolidation.
- [ ] Run tests and confirm missing profiles/policy code fail.
- [ ] Implement minimal YAML-backed profiles and Store-backed memory enforcement.
- [ ] Run focused and complete suites.

### Task 6: Product/Development/Risk LangGraph

**Files:**
- Create: `vesper/platform/validation.py`
- Create: `vesper/platform/graph.py`
- Create: `tests/platform/test_graph.py`

**Interfaces:**
- `SpecialistRunner.run(profile, specialist_input) -> SpecialistReceipt`
- `DeterministicValidator.validate(state) -> ValidationResult`
- `build_product_graph(runner, validator, checkpointer, store) -> CompiledStateGraph`
- `resume_approval(graph, thread_id, decision) -> PlatformState`

- [ ] Write deterministic routing tests for success, validation correction, risk correction, a combined three-failure stop, interrupt persistence, approval, rejection, cancellation, and process reopen.
- [ ] Run tests and confirm graph functions are absent.
- [ ] Implement explicit nodes and conditional edges with a real `interrupt()` approval node and `Command(resume=...)` recovery.
- [ ] Run focused and complete suites.

### Task 7: Typer Operator CLI

**Files:**
- Create: `vesper/platform/cli.py`
- Create: `tests/platform/test_cli.py`
- Modify: `pyproject.toml` with `v20-agent = "vesper.platform.cli:main"`.
- Modify: `README.md`

**Interfaces:**
- Commands: `run create`, `run status`, `run resume`, `run cancel`, `evidence show`, `approval list`, `approval approve`, `approval reject`.
- Global options: `--root`, `--json`, `--no-color`, and `--version`.
- Exit codes: 0 success, 1 operational failure, 2 invalid usage, 3 pending approval/operator intervention, 4 not found or corrupt state.

- [ ] Write CLI runner/subprocess tests for help purity, create/status/resume, receipt inspection, explicit approval/rejection, cancellation, JSON output, and stable state labels.
- [ ] Run tests and confirm missing commands fail.
- [ ] Implement lazy service construction so help and read-only parsing never import Tk, secrets, broker, provider, engine, or Codex runtime classes.
- [ ] Document copy/paste offline commands and authority boundaries.
- [ ] Run focused and complete suites.

### Task 8: Final Reconciliation

**Files:**
- Modify only documentation or tests directly required by discovered mismatches.

- [ ] Sync CodeGraph and inspect affected tests for new platform files.
- [ ] Run a fresh `uv sync --locked --all-groups` in an isolated environment.
- [ ] Run focused platform tests, complete `tests` suite, isolated imports, tracked and first-party compilation, Ruff lint, changed-file formatting, `uv lock --check`, isolated `uv pip check`, and `git diff --check`.
- [ ] Inspect the complete diff and confirm no trading, data, model, schedule, provider, or historical-evidence behavior changed.
- [ ] Reconcile all requested deliverables, document the LangMem blocker and residual risks, and stop before real Codex execution.
