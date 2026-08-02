# Single Qwen Runtime Implementation Plan

> **For agentic workers:** Execute task-by-task with test-driven development and fresh verification.

**Goal:** Run all autonomous roles through one local `qwen:64k` model with controller-mediated tools, strict context reserve, and one inference at a time.

**Architecture:** A local Ollama adapter returns typed tool requests but never executes host tools. The controller validates role, path, arguments, call count, and observed prompt tokens before execution. A cross-process lease serializes inference. Existing Codex/OpenCode runtimes remain manual choices and are never fallbacks.

**Tech Stack:** Python 3.11 standard-library HTTP, Ollama local API, Pydantic 2, pytest.

## Fixed limits

- Model: exactly `qwen:64k`; `num_ctx=65536`.
- Accumulated input ceiling: 49,152 tokens; output reserve: 16,384 tokens.
- Tool-call ceiling: eight per turn.
- No automatic fallback, parallel inference, arbitrary shell, arbitrary network, or direct model tool execution.

### Task 1: Context and turn contracts

**Files:** Create `vesper/platform/context_budget.py`; modify `vesper/platform/contracts.py`; create `tests/platform/test_context_budget.py`.

- [ ] Test exact limits, observed-token rejection, output reserve, and tool-count rejection.
- [ ] Add typed chat, tool-call, and usage receipts.

### Task 2: Local Ollama adapter

**Files:** Create `vesper/platform/ollama.py`; create `tests/platform/test_ollama.py`.

- [ ] Test fixed endpoint/model/options, structured response parsing, timeout, malformed output, and no fallback.
- [ ] Use an injected transport; default to loopback-only standard-library HTTP.

### Task 3: Controller tool gateway

**Files:** Create `vesper/platform/agent_tools.py`; create `tests/platform/test_agent_tools.py`.

- [ ] Test bounded read/search, Development-only compare-and-swap writes, fixed `git diff --check`, symlink/path escape, protected paths, unknown tools, and call limits.
- [ ] Execute only controller allowlisted operations; never expose a shell tool.

### Task 4: Serialized inference and service wiring

**Files:** Create `vesper/platform/qwen_runtime.py`; modify `vesper/platform/service.py`, `vesper/platform/cli.py`; create `tests/platform/test_qwen_runtime.py`; modify service/CLI tests.

- [ ] Test lease contention, stale-lease recovery, cancellation, context rejection before tool execution, and exact runtime metadata.
- [ ] Add explicit `ollama-qwen` selection while retaining existing runtimes without fallback.

