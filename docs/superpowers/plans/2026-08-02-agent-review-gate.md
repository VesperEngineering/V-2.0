# Agent Daily Review Gate Implementation Plan

> **For agentic workers:** Execute task-by-task with test-driven development and fresh verification.

**Goal:** Queue event-driven agent work, produce a sealed post-market digest, and require operator acknowledgement before new autonomous proposals are admitted.

**Architecture:** Deterministic sensors enqueue typed work; they do not run language models. A persisted priority queue feeds the single-Qwen lease. Journals render into JSON and Markdown digests. A hybrid gate blocks only new autonomous proposals when the prior session review is missing; previously admitted work and trading systems are unaffected.

**Tech Stack:** Python 3.11, SQLite Store, injected exchange-session calendar, Typer, pytest.

## Constraints

- No scheduler installation or activation.
- No broker, order, position, capital, risk-limit, training, promotion, or live-deployment action.
- Manual CLI commands expose readiness and receipts; an external scheduler may be approved separately later.

### Task 1: Persistent work queue

**Files:** Create `vesper/platform/agent_queue.py`; modify `vesper/platform/contracts.py`; create `tests/platform/test_agent_queue.py`.

- [ ] Test priority/FIFO ordering, deduplication, claim lease, retry, cancellation, reopen, and one active inference.
- [ ] Persist work items and claims in isolated Store namespaces.

### Task 2: Session cadence policy

**Files:** Create `vesper/platform/cadence.py`; create `tests/platform/test_cadence.py`.

- [ ] Test action-only, event-driven, close-plus-15-min digest eligibility, holiday/weekend handling through an injected calendar, and no timer side effects.
- [ ] Return decisions only; never install or start a scheduler.

### Task 3: Digest and operator receipts

**Files:** Create `vesper/platform/review.py`; create `tests/platform/test_review.py`.

- [ ] Test eight sections, journal-chain verification, stable rendering, content hash, corrections, acknowledgement, and tamper rejection.
- [ ] Store canonical JSON plus readable Markdown and immutable review receipts under platform state.

### Task 4: Hybrid gate and CLI

**Files:** Modify `vesper/platform/service.py`, `vesper/platform/cli.py`; modify service/CLI tests.

- [ ] Test bootstrap, blocked/unblocked admission, protected approval remaining separate, and prior admitted work continuing.
- [ ] Add manual queue, digest, review, and gate-status commands without scheduler activation.

