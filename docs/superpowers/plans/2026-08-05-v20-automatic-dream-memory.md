# V20 Automatic Dream Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every completed V20 Qwen chat persist its transcript, run Dream Gate on exit, automatically write stable memory/procedure learnings into the V20 knowledge vault, and load those learnings in the next chat.

**Architecture:** `SessionRecorder` remains the immediate cold transcript store. `DreamGate` becomes an automatic consolidation pass that writes an immutable report plus approved Markdown notes for ordinary memory and procedures. Chat startup reads approved knowledge into context; controller/tool authority remains enforced outside the memory files.

**Tech Stack:** Python 3.12, Pydantic contracts, PyYAML Markdown frontmatter, Ollama `qwen:64k`, pytest, `uv run --locked`.

## Global Constraints

- Preserve existing unrelated dirty work.
- Never write under `vesper/data/massive/` or `vesper/data/model_research/`.
- Do not expose credentials, hidden reasoning, or raw protected data in transcripts or memory.
- Automatic memory may update only `knowledge/memory/` and `knowledge/skills/` with valid V20 frontmatter.
- Dream memory does not grant broker, credential, protected-data, scheduler, risk, trading, deletion, or deployment authority.
- Every completed chat event is durable before the next prompt is accepted; normal EOF, `/quit`, and Ctrl+C trigger consolidation.

## File Map

- Modify `vesper/platform/contracts.py`: represent applied dream proposals and report receipts.
- Modify `vesper/platform/dreaming.py`: generate and apply stable memory/procedure notes with provenance.
- Modify `vesper/platform/chat.py`: run consolidation on normal chat termination and include approved knowledge at startup.
- Modify `vesper/platform/service.py`: expose the automatic Dream Gate behavior through the existing chat service without adding a scheduler.
- Modify `vesper/platform/cli.py` and `knowledge/README.md`: describe the new behavior and command output accurately.
- Modify `tests/platform/test_dreaming.py`: prove automatic application, provenance, replacement, and disallowed targets.
- Modify `tests/platform/test_chat.py`: prove close-triggered dreaming and next-session memory loading.
- Modify `tests/platform/test_contracts.py`: update the report contract for applied changes.

### Task 1: Define the automatic dream receipt

**Files:** `vesper/platform/contracts.py`, `tests/platform/test_contracts.py`

- [ ] Add a frozen `DreamAppliedChange` contract containing proposal ID, target, action, and resulting SHA-256.
- [ ] Add `applied_changes` to `DreamGateReport` and preserve source receipt validation.
- [ ] Write and run a failing round-trip test.
- [ ] Implement the smallest contract change and run the focused contract tests.

### Task 2: Apply ordinary dream learnings to the vault

**Files:** `vesper/platform/dreaming.py`, `tests/platform/test_dreaming.py`

- [ ] Write failing tests for approved memory/procedure note creation, existing-note replacement, and rejection of non-memory/skill targets.
- [ ] Add deterministic Markdown frontmatter using `vesper_id`, `vesper_kind`, `vesper_status: approved`, `vesper_scope`, `title`, and dream provenance.
- [ ] Generate note bodies from the model summary/evidence, never raw transcript text.
- [ ] Atomically replace only the requested `knowledge/memory/` or `knowledge/skills/` note; keep the immutable dream report.
- [ ] Return applied-change receipts and record failures as report limitations without deleting prior notes.
- [ ] Run focused Dream Gate tests.

### Task 3: Consolidate when Qwen Chat closes

**Files:** `vesper/platform/chat.py`, `tests/platform/test_chat.py`

- [ ] Write a failing test proving EOF and `/quit` call Dream Gate after completed events and leave a report plus applied note.
- [ ] Add a `finally` close path that runs Dream Gate only after at least one recorded event; catch consolidation errors after the transcript is safe and report them to the user.
- [ ] Keep each event write immediate so an interrupted request cannot erase earlier turns.
- [ ] Run focused chat tests.

### Task 4: Load learned memory in the next chat

**Files:** `vesper/platform/chat.py`, `tests/platform/test_chat.py`, `knowledge/README.md`

- [ ] Write a failing test showing an approved dream note is present in the next chat system context.
- [ ] Add a bounded active-knowledge section to `load_chat_context`, using the existing V20 approved-document loader and current context budget.
- [ ] Keep skills role-scoped and memory available as V20 context; do not treat notes as controller permissions.
- [ ] Update documentation and run chat/knowledge tests.

### Task 5: Fresh verification and closeout

- [ ] Run focused tests for contracts, dreaming, chat, and knowledge.
- [ ] Run the smallest broader platform test slice justified by the changed interfaces.
- [ ] Inspect the diff and classify pre-existing dirty files separately from this change.
- [ ] Run the repository closeout check only if the source tree is clean; do not clean unrelated user changes.

