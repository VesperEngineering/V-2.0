# Core Quant Agent Team Implementation Plan

> **For agentic workers:** Execute task-by-task with test-driven development and fresh verification.

**Goal:** Engineer the five missing core quant agents as bounded, proposal-only Qwen roles with separate context, tools, memory, and journals.

**Architecture:** Native profiles define purpose and prohibitions. An autonomous runner loads one profile, retrieves role-scoped evidence, calls the single-Qwen runtime, validates a typed role output, routes proposals through the controller, and journals every material step. The agents are separate from the existing seven-node workflow until a later approved topology change.

**Tech Stack:** YAML profiles, Pydantic 2, single-Qwen runtime, SQLite Store, pytest.

## Roster

- Quant Research Lead: frames hypotheses, ranks research, and routes tasks.
- Model Researcher: analyzes approved model/data evidence; cannot train or promote.
- Independent Quant Validator: independently challenges evidence and assumptions; cannot approve its own work.
- Portfolio Researcher: studies exposures and allocation proposals; cannot change capital or risk limits.
- Execution & Performance Analyst: studies fills, costs, slippage, and outcomes; cannot place or alter orders.

### Task 1: Native profiles and role schemas

**Files:** Create five `profiles/native/v20-*/SOUL.md` and `profile.yaml` pairs; create `vesper/platform/agent_profiles.py`; create `tests/platform/test_agent_profiles.py`.

- [ ] Test exact model, role, tools, skills, prohibitions, and profile hashes for all eight roles.
- [ ] Reject stale, extra, unsafe, or mismatched profile fields.

### Task 2: Typed role outputs

**Files:** Create `vesper/platform/quant_agents.py`; create `tests/platform/test_quant_agents.py`.

- [ ] Test hypotheses/priorities, model findings, validation challenges, portfolio exposures, and execution diagnostics.
- [ ] Require evidence references, confidence, limitations, and proposal objects; forbid acceptance authority.

### Task 3: Autonomous runner

**Files:** Create `vesper/platform/agent_runner.py`; create `tests/platform/test_agent_runner.py`.

- [ ] Test isolated namespaces, skill injection, bounded evidence, structured Qwen calls, proposal routing, journal coverage, retries, and fail-closed invalid output.
- [ ] Never pass producer reasoning to the independent validator; pass evidence and claims only.

### Task 4: Roster service and CLI

**Files:** Modify `vesper/platform/service.py`, `vesper/platform/cli.py`; modify service/CLI tests.

- [ ] Test roster/list/show/run/status paths and explicit role selection.
- [ ] Keep all five agents action-only until separately approved scheduler activation.

### Task 5: Final verification

- [ ] Run focused tests after each task, then the full suite, Ruff, compilation, lock check, import-boundary checks, and `git diff --check`.
- [ ] Inspect the complete diff for authority expansion, protected-data writes, silent fallback, scheduler activation, or trading-path imports.
- [ ] Record exact receipts and residual limits; do not claim live readiness.

