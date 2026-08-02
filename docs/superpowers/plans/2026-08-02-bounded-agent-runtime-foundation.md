# Bounded Agent Runtime Foundation Implementation Plan

> **For agentic workers:** Execute task-by-task with test-driven development and fresh verification.

**Goal:** Add an eight-role authority model, proposal routing, and immutable per-agent journals without changing the existing seven-node workflow topology.

**Architecture:** Keep `SpecialistRole` stable for the existing graph. Add a separate eight-role `AgentRole`, deterministic controller-owned authority routing, and append-only hash-chained journal records stored in the existing SQLite Store. Agent output is advisory until the controller admits it.

**Tech Stack:** Python 3.11, Pydantic 2, LangGraph SQLite Store, pytest.

## Constraints

- No broker, order, credential, provider, risk-limit, model-promotion, scheduler, or protected-data authority.
- No writes below `vesper/data/massive/` or `vesper/data/model_research/`.
- Preserve the existing Product/Development/Risk workflow contracts.

### Task 1: Restore a truthful baseline

**Files:** Modify `tests/platform/test_service.py` only.

- [ ] Add a temporary synthetic Massive SQLite and split-adjustment fixture outside protected repository data.
- [ ] Pass it only to service tests that intend to exercise later workflow stages.
- [ ] Confirm the five baseline failures pass without weakening production checks.

### Task 2: Typed agent authority contracts

**Files:** Modify `vesper/platform/contracts.py`; modify `tests/platform/test_contracts.py`.

- [ ] Test and add the eight-role roster, proposal capabilities, authority classes, proposal status, routing decision, and journal event contracts.
- [ ] Keep every contract frozen, extra-forbidden, versioned, and JSON-round-trippable.

### Task 3: Deterministic proposal router

**Files:** Create `vesper/platform/authority.py`; create `tests/platform/test_authority.py`.

- [ ] Test safe, protected, denied, role-mismatch, missing-evidence, and unknown-capability routes.
- [ ] Implement an explicit allowlist; protected proposals require operator approval and denied proposals cannot execute.

### Task 4: Append-only agent journals

**Files:** Create `vesper/platform/journals.py`; create `tests/platform/test_journals.py`.

- [ ] Test namespace isolation, hash chaining, reopen, idempotent replay, conflict rejection, and correction events.
- [ ] Implement create-only canonical JSON journal events over `LangGraphStoreAdapter`.

### Task 5: Existing specialist integration

**Files:** Modify `vesper/platform/composition.py`; modify `vesper/platform/service.py`; modify `tests/platform/test_composition.py` and `tests/platform/test_service.py`.

- [ ] Inject a journal port and record proposed, routed, validation, risk, and operator decisions.
- [ ] Preserve existing receipts and lifecycle behavior.

