# V20 Ratatui Continuous Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete continuous governed agents, separate chats, bounded Qwen context, V20-only working memory, notifications, backup/recovery, safe local code maintenance, packaging, and final performance verification.

**Architecture:** A controller-owned operations daemon may outlive the TUI and runs only capabilities explicitly enabled by its policy. Conversation, working-memory, backup, notification, and maintenance services expose typed ports to the gateway. Rust remains a client. Sensitive or unavailable services remain disabled until their runtime prerequisites and authority gates pass.

**Tech Stack:** Earlier phase stack plus Python WinRT 3.2.1 notifications, Windows DPAPI through pywin32, SQLite, Obsidian-compatible Markdown, Git worktrees, PowerShell packaging, and Windows Task-free process supervision.

**Status:** Approved; preflight corrections incorporated.

## Global Constraints

- Complete the foundation, observability, and controls plans first.
- The operations daemon starts only through a confirmed V20 Start command; opening the TUI alone starts only the control gateway.
- Closing the TUI does not stop an already started operations daemon.
- Do not create a Windows scheduled task or service.
- Quiet Mode is 7:00 PM through 8:00 AM America/New_York and all weekend.
- Only one `qwen:64k` inference runs at a time.
- Auto-compress one agent at 80 percent of `MAX_INPUT_TOKENS`; preserve raw chats.
- Core working memory is V20-only and at most 2,000 words. Repository knowledge and `AGENTS.md` remain separate and authoritative.
- Working-memory changes are reversible and are not approved repository knowledge.
- Candidate training and evaluation run only through an approved `CandidateTrainingPort`; the default port is unavailable.
- Runtime start authority, continuous-work scheduling, daily memory curation,
  candidate training, candidate deletion, and automatic merge are separate
  controller-owned `ActivationGrant` values. Every grant defaults disabled with
  no receipt. An available adapter never changes a grant and never implies approval.
- Notifications contain only `V20 needs attention`.
- Backup uses current-user DPAPI, excludes credentials and protected source data, and restores only while runtime is stopped.
- Automatic code maintenance never edits main directly, never pushes, and never touches forbidden authority scopes.
- The current dirty main disables automatic merge.
- No task accesses a broker, account, credential, real order, or real money.
- Run every pytest command with `TEMP` and `TMP` set to
  `C:\tmp\v20-tui-operations-temp`, `--basetemp
  C:\tmp\v20-tui-operations-pytest`, and `-o
  cache_dir=C:\tmp\v20-tui-operations-cache`.
- Use test-first changes and one Conventional Commit per task.

---

## File map

```text
vesper/platform/ops/
|-- __init__.py
|-- cli.py                    long-running local daemon entrypoint
|-- supervisor.py             bounded priority loop
|-- policy.py                 quiet mode, resources, queue, rest
|-- activation.py             disabled-by-default receipt-bound grants
|-- services.py               health and one-restart policy
`-- training.py               unavailable/approved training port

vesper/platform/tui/
|-- conversations.py          per-agent raw chat ledger
|-- compression.py            bounded context summaries
|-- working_memory.py         2,000-word core and archive
|-- notifications.py          generic Windows toast
|-- candidate_retention.py    30/90-day model candidate cleanup
|-- backup.py                 DPAPI archive and restore
|-- recovery.py               unclean-stop validation
|-- retention.py              permanent history and raw-log compression
|-- maintenance.py            low-risk worktree/merge policy
|-- git_port.py               direct-argument local Git adapter
`-- snapshot_cache.py         current-user encrypted cached view

tests/platform/ops/
|-- test_supervisor.py
|-- test_policy.py
|-- test_services.py
`-- test_training.py

tests/platform/tui/
|-- test_conversations.py
|-- test_compression.py
|-- test_working_memory.py
|-- test_notifications.py
|-- test_candidate_retention.py
|-- test_backup.py
|-- test_recovery.py
|-- test_retention.py
|-- test_maintenance.py
|-- test_git_port.py
|-- test_snapshot_cache.py
`-- test_tui_scripts.py

TUI testing/ratatui-console/
|-- src/chat.rs
|-- src/screens/memory.rs
|-- src/screens/system.rs
|-- tests/operations.rs
`-- tests/performance.rs

scripts/
|-- build-tui.ps1
|-- install-tui-shortcut.ps1
`-- verify-tui.ps1
```

### Task 1: Pin Windows notification dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `tests/platform/test_dependencies.py`

**Interfaces:**
- Produces Windows-only pins `winrt-runtime==3.2.1`, `winrt-Windows.Data.Xml.Dom==3.2.1`, and `winrt-Windows.UI.Notifications==3.2.1`.

- [ ] **Step 1: Add the failing exact-pin test**

```python
import tomllib
from pathlib import Path


def test_tui_notification_dependencies_are_windows_only() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project_dependencies = tuple(project["project"]["dependencies"])
    required = {
        "winrt-runtime==3.2.1; sys_platform == 'win32'",
        "winrt-Windows.Data.Xml.Dom==3.2.1; sys_platform == 'win32'",
        "winrt-Windows.UI.Notifications==3.2.1; sys_platform == 'win32'",
    }
    assert required.issubset(set(project_dependencies))
```

- [ ] **Step 2: Run the test and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/test_dependencies.py -q`

Expected: FAIL because pins are absent.

- [ ] **Step 3: Add exact Windows markers and refresh the lock**

Run: `uv lock`

```toml
"winrt-runtime==3.2.1; sys_platform == 'win32'",
"winrt-Windows.Data.Xml.Dom==3.2.1; sys_platform == 'win32'",
"winrt-Windows.UI.Notifications==3.2.1; sys_platform == 'win32'",
```

- [ ] **Step 4: Run the test and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/test_dependencies.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- 'pyproject.toml' 'uv.lock' 'tests/platform/test_dependencies.py'
git commit -m "build(tui): pin Windows notification support"
```

### Task 2: Store separate agent conversations and bounded summaries

**Files:**
- Create: `vesper/platform/tui/conversations.py`
- Create: `vesper/platform/tui/compression.py`
- Modify: `vesper/platform/tui/command_ports.py`
- Modify: `vesper/platform/tui/command_registry.py`
- Create: `tests/platform/tui/test_conversations.py`
- Create: `tests/platform/tui/test_compression.py`
- Create: `TUI testing/ratatui-console/src/chat.rs`
- Create: `TUI testing/ratatui-console/tests/chat.rs`

**Interfaces:**
- Produces `ConversationStore.start_message`, `append_chunk`, `complete`, `interrupt`, and `history`.
- Produces statuses `draft`, `complete`, and `interrupted`.
- Produces `CompressionPolicy.should_compress(prompt_tokens) -> bool`.
- Produces `ContextCompressor.build(agent_id, objective) -> CompressedContext`.
- Produces `MemoryCommandPort.compress_now(command_id, agent_id) ->
  CompressionReceipt`; the registry enables only `memory.compress-now` when
  this port is healthy.

```python
class ConversationStore:
    def start_message(self, agent_id: SafeId, role: Literal["human", "agent"], created_at_utc: datetime) -> MessageView: ...
    def append_chunk(self, message_id: SafeId, sequence: int, text: str) -> MessageView: ...
    def complete(self, message_id: SafeId, validation_receipt_id: SafeId, completed_at_utc: datetime) -> MessageView: ...
    def interrupt(self, message_id: SafeId, interrupted_at_utc: datetime) -> MessageView: ...
    def history(self, agent_id: SafeId, limit: int, cursor: SafeId | None) -> tuple[MessageView, ...]: ...

class CompressionPolicy:
    def should_compress(self, prompt_tokens: int) -> bool: ...

class ContextCompressor:
    def build(self, agent_id: SafeId, objective: str) -> CompressedContext: ...

class MemoryCommandPort(Protocol):
    def compress_now(self, command_id: SafeId, agent_id: SafeId) -> CompressionReceipt: ...
```

- [ ] **Step 1: Write append, stream, interruption, and compression tests**

Assert each agent has a separate thread; only human/agent roles exist; chunks
append in sequence; completed output cannot change; disconnect leaves draft as
interrupted; raw text survives compression; compression starts at
`floor(MAX_INPUT_TOKENS * 0.80)`; and the summary retains objective, current
state, unresolved decisions, approvals, evidence IDs, errors, blockers,
applicable rules, core-memory IDs, and raw-message pointers.

```python
def test_compression_preserves_raw_chat_and_required_context(store, compressor) -> None:
    message = store.start_message("v20-product", "agent", UTC_NOW)
    store.append_chunk(message.message_id, 1, "raw output")
    context = compressor.build("v20-product", "objective")
    assert store.history("v20-product", 10, None)[0].text == "raw output"
    assert context.objective == "objective"
```

- [ ] **Step 2: Run Python and Rust chat tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_conversations.py tests/platform/tui/test_compression.py -q`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test chat --locked`

Expected: FAIL because chat storage is absent.

- [ ] **Step 3: Implement the SQLite chat ledger**

Use immutable message rows plus ordered chunk rows. Store agent ID, role,
created/completed timestamps, validation state, token counts, and context-summary
lineage. Never store private chain-of-thought fields. `complete` requires the
controller's validation receipt ID.

```python
def complete(self, message_id: SafeId, validation_receipt_id: SafeId, completed_at_utc: datetime) -> MessageView:
    with self._connection:
        message = self._require_status(message_id, "draft")
        return self._set_terminal(message, "complete", validation_receipt_id, completed_at_utc)
```

- [ ] **Step 4: Implement per-agent hidden chat UI**

Open chat only from an agent card or explicit agent selector. Render streamed
content as `DRAFT`; replace with `COMPLETE` only on a complete event; retain
`INTERRUPTED` output in history. `Enter` sends only when input owns focus.

```rust
use std::collections::BTreeMap;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ChatStatus {
    Draft,
    Complete,
    Interrupted,
}

impl ChatStatus {
    pub const fn label(self) -> &'static str {
        match self {
            Self::Draft => "DRAFT",
            Self::Complete => "COMPLETE",
            Self::Interrupted => "INTERRUPTED",
        }
    }
}

pub enum ChatOpenSource {
    AgentCard,
    AgentSelector,
}

pub enum ChatEvent {
    Chunk { agent_id: String, message_id: String, text: String },
    Complete { agent_id: String, message_id: String },
    Interrupted { agent_id: String, message_id: String },
}

pub struct ChatInput {
    pub owns_focus: bool,
    pub text: String,
}

pub enum ChatAction {
    Send { agent_id: String, text: String },
}

pub struct ChatMessage {
    pub message_id: String,
    pub text: String,
    pub status: ChatStatus,
}

#[derive(Default)]
pub struct ChatThread {
    pub messages: Vec<ChatMessage>,
}

impl ChatThread {
    fn append_chunk(&mut self, message_id: String, text: String, status: ChatStatus) {
        if let Some(message) = self.messages.iter_mut().find(|item| item.message_id == message_id) {
            if message.status == ChatStatus::Draft {
                message.text.push_str(&text);
            }
            return;
        }
        self.messages.push(ChatMessage { message_id, text, status });
    }

    fn set_terminal(&mut self, message_id: String, status: ChatStatus) {
        if let Some(message) = self.messages.iter_mut().find(|item| item.message_id == message_id) {
            if message.status == ChatStatus::Draft {
                message.status = status;
            }
        }
    }
}

#[derive(Default)]
pub struct ChatState {
    visible_agent: Option<String>,
    threads: BTreeMap<String, ChatThread>,
}

impl ChatState {
    pub fn open(&mut self, agent_id: String, source: ChatOpenSource) {
        match source {
            ChatOpenSource::AgentCard | ChatOpenSource::AgentSelector => {
                self.visible_agent = Some(agent_id);
            }
        }
    }

    pub fn reduce(&mut self, event: ChatEvent) {
        match event {
            ChatEvent::Chunk { agent_id, message_id, text } => {
                self.thread_mut(&agent_id).append_chunk(message_id, text, ChatStatus::Draft);
            }
            ChatEvent::Complete { agent_id, message_id } => {
                self.thread_mut(&agent_id).set_terminal(message_id, ChatStatus::Complete);
            }
            ChatEvent::Interrupted { agent_id, message_id } => {
                self.thread_mut(&agent_id).set_terminal(message_id, ChatStatus::Interrupted);
            }
        }
    }

    pub fn enter(&self, input: &ChatInput) -> Option<ChatAction> {
        if !input.owns_focus || input.text.is_empty() {
            return None;
        }
        Some(ChatAction::Send {
            agent_id: self.visible_agent.clone()?,
            text: input.text.clone(),
        })
    }

    fn thread_mut(&mut self, agent_id: &str) -> &mut ChatThread {
        self.threads.entry(agent_id.to_owned()).or_default()
    }
}
```

- [ ] **Step 5: Run tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_conversations.py tests/platform/tui/test_compression.py -q`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test chat --locked`

Expected: PASS including reopen and 64K-context boundary cases.

Assert the phase-3 unavailable memory port becomes enabled only when the real
compression adapter is injected. A disabled port calls no compressor; an enabled
command uses its command ID as the idempotency key and returns one durable
receipt.

- [ ] **Step 6: Commit**

```powershell
git add -- 'vesper/platform/tui/conversations.py' 'vesper/platform/tui/compression.py' 'vesper/platform/tui/command_ports.py' 'vesper/platform/tui/command_registry.py' 'tests/platform/tui/test_conversations.py' 'tests/platform/tui/test_compression.py' 'TUI testing/ratatui-console/src/chat.rs' 'TUI testing/ratatui-console/tests/chat.rs'
git commit -m "feat(tui): preserve separate agent conversations"
```

### Task 3: Implement V20-only 2,000-word working memory

**Files:**
- Create: `vesper/platform/tui/working_memory.py`
- Create: `tests/platform/tui/test_working_memory.py`
- Modify: `TUI testing/ratatui-console/src/screens/memory.rs`

**Interfaces:**
- Produces `WorkingMemoryStore.propose`, `curate`, `core`, `archive`, `history`, and `rollback`.
- Produces `MemoryValueScore` from evidence, usefulness, reuse, relevance, age, and safety rarity.
- Uses default vault `%USERPROFILE%\Documents\V20 Qwen Vault`.

```python
class WorkingMemoryStore:
    def propose(self, candidate: MemoryCandidate) -> MemoryProposal: ...
    def curate(self, trigger: Literal["validated-work", "daily"]) -> MemoryChangeReceipt: ...
    def core(self) -> tuple[MemoryItem, ...]: ...
    def archive(self, query: str, limit: int = 100) -> tuple[MemoryItem, ...]: ...
    def history(self, limit: int = 100) -> tuple[MemoryChangeReceipt, ...]: ...
    def rollback(self, change_id: SafeId) -> MemoryChangeReceipt: ...

@dataclass(frozen=True, slots=True)
class MemoryValueScore:
    evidence: int
    usefulness: int
    reuse: int
    relevance: int
    age: int
    safety_rarity: int
```

- [ ] **Step 1: Write scope, limit, archive, and authority tests**

Reject non-V20 content, secrets, task progress, temporary blockers, unsupported
claims, and any write to repository `knowledge/`. Count words with Unicode word
boundaries and require core count `<= 2000`. Assert stronger candidates may
replace lower-value items, rare safety facts receive a protected score floor,
demoted items move to archive, every mutation records evidence/reason, and
rollback restores the prior core exactly. The contract has no manual pin field.

```python
def test_core_is_v20_only_bounded_and_reversible(store) -> None:
    change = store.curate("validated-work")
    assert word_count(store.core()) <= 2000
    assert all(item.scope == "v20" for item in store.core())
    assert store.rollback(change.change_id).restored_hash == change.before_hash
```

- [ ] **Step 2: Run tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_working_memory.py -q`

Expected: FAIL because working memory is absent.

- [ ] **Step 3: Implement Obsidian-compatible files plus a SQLite ledger**

Write `Core Memory.md`, `Archive/{memory_id}.md`, and `History/{change_id}.md`
atomically. Front matter contains ID, status, created/updated UTC, evidence IDs,
score components, supersedes, and content hash. Core rules and `AGENTS.md` are
read-only inputs and do not count toward 2,000 words.

```python
def _atomic_replace(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _restore_before_images(before: dict[Path, bytes | None]) -> None:
    for path, payload in before.items():
        if payload is None:
            path.unlink(missing_ok=True)
        else:
            _atomic_replace(path, payload)


def _apply_change(self, change: MemoryChange, writes: dict[Path, bytes]) -> MemoryChangeReceipt:
    before = {path: path.read_bytes() if path.exists() else None for path in writes}
    self._ledger.record_prepared(change, before, writes)  # durable PREPARED row first
    try:
        for path, payload in writes.items():
            _atomic_replace(path, payload)
        receipt = MemoryChangeReceipt.from_change(change)
        with self._ledger.transaction():
            self._ledger.insert_receipt(receipt)  # receipt uses change.change_id
            self._ledger.mark_committed(change.change_id)
        return receipt
    except BaseException:
        _restore_before_images(before)  # restore files before recording rollback
        with self._ledger.transaction():
            self._ledger.mark_rolled_back(change.change_id)
        raise


def repair_prepared_changes(self) -> None:
    for prepared in self._ledger.prepared_changes():
        _restore_before_images(prepared.before)
        with self._ledger.transaction():
            self._ledger.mark_rolled_back(prepared.change_id)
```

- [ ] **Step 4: Implement controller-invoked curation**

Allow `curate(trigger="validated-work")` after validated completed work. Expose
`curate(trigger="daily")` for Task 4, but do not schedule it here. Choose the
highest-value set within 2,000 words using deterministic score then memory ID
tie-break. Qwen may propose text; the controller validates scope/evidence and
makes the final file change. This store never calls `knowledge-sync` and never
marks repository knowledge approved. Task 4 may call the daily trigger only when
the separate validated daily-curation grant is enabled.

```python
def curate(self, trigger: Literal["validated-work", "daily"]) -> MemoryChangeReceipt:
    candidates = self._validated_v20_candidates(trigger)
    selected = deterministic_knapsack(candidates, max_words=2000)
    return self._atomic_replace_core_and_archive(selected, trigger)
```

- [ ] **Step 5: Run tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_working_memory.py -q`

Expected: PASS including crash between file and ledger update with repair on
reopen.

- [ ] **Step 6: Commit**

```powershell
git add -- 'vesper/platform/tui/working_memory.py' 'tests/platform/tui/test_working_memory.py' 'TUI testing/ratatui-console/src/screens/memory.rs'
git commit -m "feat(tui): add bounded V20 working memory"
```

### Task 4: Define operations activation and scheduling policy

**Files:**
- Create: `vesper/platform/ops/__init__.py`
- Create: `vesper/platform/ops/activation.py`
- Create: `vesper/platform/ops/policy.py`
- Create: `vesper/platform/ops/training.py`
- Create: `tests/platform/ops/test_policy.py`
- Create: `tests/platform/ops/test_activation.py`
- Create: `tests/platform/ops/test_training.py`

**Interfaces:**
- Produces frozen `OperationsActivation` whose six fields are exact
  `ActivationGrant` values.
- Produces `OperationsActivationStore.current() -> OperationsActivation`; this
  plan exposes no TUI command that changes activation.
- Produces `OperationsPolicy.next_action(state, now_utc) -> ActionDecision`.
- Produces `QwenWorkPort.available()` and `run_one(work_item)`.
- Produces `CandidateTrainingPort.available()` and `train_and_evaluate(request)`.

```python
class ActivationGrant(StrictModel):
    enabled: bool = False
    receipt_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def require_receipt_iff_enabled(self) -> "ActivationGrant":
        if self.enabled != (self.receipt_id is not None):
            raise ValueError("activation-receipt-invariant")
        return self

class ActivationCapability(StrEnum):
    RUNTIME_START = "runtime_start"
    CONTINUOUS_WORK = "continuous_work"
    DAILY_MEMORY_CURATION = "daily_memory_curation"
    CANDIDATE_TRAINING = "candidate_training"
    CANDIDATE_DELETION = "candidate_deletion"
    AUTOMATIC_MERGE = "automatic_merge"

class OperationsActivation(StrictModel):
    runtime_start: ActivationGrant = Field(default_factory=ActivationGrant)
    continuous_work: ActivationGrant = Field(default_factory=ActivationGrant)
    daily_memory_curation: ActivationGrant = Field(default_factory=ActivationGrant)
    candidate_training: ActivationGrant = Field(default_factory=ActivationGrant)
    candidate_deletion: ActivationGrant = Field(default_factory=ActivationGrant)
    automatic_merge: ActivationGrant = Field(default_factory=ActivationGrant)

class OperationsActivationStore:
    def current(self) -> OperationsActivation: ...

    def validated_grant(self, capability: ActivationCapability) -> ActivationGrant:
        grant = getattr(self.current(), capability.value)
        if not grant.enabled:
            return grant
        self._authority_receipts.require(capability, grant.receipt_id)
        return grant

class OperationsPolicy:
    def next_action(self, state: OperationsState, now_utc: datetime) -> ActionDecision: ...

class QwenWorkPort(Protocol):
    def available(self) -> CapabilityView: ...
    def run_one(self, work_item: WorkItem) -> WorkReceipt: ...

class CandidateTrainingPort(Protocol):
    def available(self) -> CapabilityView: ...
    def train_and_evaluate(self, request: CandidateTrainingRequest) -> CandidateTrainingReceipt: ...
```

- [ ] **Step 1: Write deterministic priority and quiet-mode tests**

Test priority order: incident, approval, portfolio, operator command, normal
queue, research backlog. Test Quiet Mode at 18:59, 19:00, 07:59, 08:00 ET,
weekends, and DST transitions. Test lower GPU budget and longer pause in quiet
mode, temperature/memory/disk/error rest, global/per-agent queue caps, duplicate
merge, backlog overflow, and one Qwen lease. A broker-position mismatch must idempotently enqueue one urgent
Reconciliation Agent task owned by the source adapter and block new order or
rebalance admission while other work continues. When resources allow and an
approved training port is available, one candidate request may run; it must bind
the approved model family, strategy, features, data identity, evaluation
contract, and artifact root.

Add a complete activation matrix. With an available Qwen adapter and queued
work, a disabled `continuous_work` grant admits zero background work. With an
available training adapter, a disabled `candidate_training` grant makes zero
training calls. A daily boundary with a disabled `daily_memory_curation` grant
makes zero curation calls. Runtime Start is eligible only through the validated
`runtime_start` store grant. Missing or mismatched receipt IDs fail closed.

```python
@pytest.mark.parametrize("field", tuple(ActivationCapability))
def test_enabled_activation_requires_matching_receipt(field, activation_store, adapters) -> None:
    with pytest.raises(ValidationError, match="activation-receipt-invariant"):
        ActivationGrant(enabled=True, receipt_id=None)
    activation_store.replace(field, ActivationGrant(enabled=True, receipt_id="wrong"))
    decision = OperationsPolicy(activation_store, adapters).next_action(active_state(), UTC_NOW)
    assert decision.kind == "rest"
    assert adapters.side_effect_calls == 0
```

- [ ] **Step 2: Run operations tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/ops/test_policy.py tests/platform/ops/test_activation.py tests/platform/ops/test_training.py -q`

Expected: FAIL because operations service is absent.

- [ ] **Step 3: Implement the pure policy and unavailable training port**

Normal mode checks priority after each bounded unit and rests at least 2 seconds
between background units. Quiet mode rests at least 30 seconds and allows one
background unit before rechecking. Resource thresholds come from typed config
with conservative defaults and appear on System. `UnavailableTrainingPort`
returns `No approved candidate training adapter is configured.` and starts no
process. `UnavailableQwenWorkPort` returns `The qwen:64k runtime adapter is not
configured.` and prevents continuous agent admission without marking queued work
failed.

`OperationsPolicy.next_action` calls `activation_store.validated_grant` before
adapter availability.
Incident and explicit operator-command handling remain available inside an
authorized running daemon, but research backlog and normal autonomous queue work
require an enabled validated `continuous_work` grant; daily curation requires an
enabled validated `daily_memory_curation` grant; candidate work requires enabled
validated `continuous_work` and `candidate_training` grants.

```python
def next_action(self, state: OperationsState, now_utc: datetime) -> ActionDecision:
    continuous = self._activation_store.validated_grant(ActivationCapability.CONTINUOUS_WORK)
    training = self._activation_store.validated_grant(ActivationCapability.CANDIDATE_TRAINING)
    if state.has_incident:
        return ActionDecision.handle_incident()
    if not continuous.enabled:
        return ActionDecision.rest()
    if state.daily_curation_due:
        daily = self._activation_store.validated_grant(ActivationCapability.DAILY_MEMORY_CURATION)
        return ActionDecision.curate_memory() if daily.enabled else ActionDecision.rest()
    if state.next_item.kind == "candidate" and not training.enabled:
        return ActionDecision.rest()
    return self._select_priority(state, now_utc)
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/ops/test_policy.py tests/platform/ops/test_activation.py tests/platform/ops/test_training.py -q`

Expected: PASS with fake Qwen, fake queues, fake resources, and fake training.

- [ ] **Step 5: Commit**

```powershell
git add -- 'vesper/platform/ops/__init__.py' 'vesper/platform/ops/activation.py' 'vesper/platform/ops/policy.py' 'vesper/platform/ops/training.py' 'tests/platform/ops/test_policy.py' 'tests/platform/ops/test_activation.py' 'tests/platform/ops/test_training.py'
git commit -m "feat(ops): define bounded operations policy"
```

### Task 5: Run the governed operations daemon and service lifecycle

**Files:**
- Create: `vesper/platform/ops/services.py`
- Create: `vesper/platform/ops/supervisor.py`
- Create: `vesper/platform/ops/cli.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `vesper/platform/tui/command_ports.py`
- Modify: `vesper/platform/tui/command_registry.py`
- Modify: `vesper/platform/tui/gateway.py`
- Create: `tests/platform/ops/test_services.py`
- Create: `tests/platform/ops/test_supervisor.py`

**Interfaces:**
- Produces script `vesper-ops-daemon`.
- Produces `OperationsSupervisor.run(stop_event) -> None`.
- Produces one-restart `ServiceSupervisor.handle_failure(service_id)`.
- Produces runtime and service command ports registered only when activation,
  authority receipt, and adapter health all pass.

```python
class OperationsSupervisor:
    def run(self, stop_event: threading.Event) -> None: ...

class ServiceSupervisor:
    def handle_failure(self, service_id: SafeId) -> ServiceRecoveryReceipt: ...

class RuntimeCommandPort(Protocol):
    def start(self, command_id: SafeId, mode: Literal["shadow", "paper"], activation_receipt_id: SafeId | None) -> RuntimeReceipt: ...
    def stop_safe(self, command_id: SafeId) -> RuntimeReceipt: ...
    def stop_force(self, command_id: SafeId) -> RuntimeReceipt: ...
    def prepare_shutdown(self, command_id: SafeId) -> RuntimeReceipt: ...

class ServiceCommandPort(Protocol):
    def pause(self, command_id: SafeId, service_id: SafeId) -> ServiceReceipt: ...
    def restart(self, command_id: SafeId, service_id: SafeId) -> ServiceReceipt: ...
```

- [ ] **Step 1: Write daemon, command-routing, and restart tests**

Assert a disabled runtime-start grant makes zero launches; an enabled grant with
a mismatched authority receipt also makes zero launches. With exact fake authority,
Start launches one direct argv, a named mutex blocks duplicates, one crash gets
one safe restart, a second failure alerts, the daemon survives TUI/gateway exit,
and Prepare for PC Shutdown checkpoints and returns `SAFE TO SHUT DOWN`.

```python
def test_runtime_start_reads_only_validated_store_grant(fake_launcher, activation_store) -> None:
    activation_store.set_runtime_start(ActivationGrant())
    assert RuntimeAdapter(activation_store, fake_launcher).start("cmd-1", "shadow", None).accepted is False
    activation_store.set_runtime_start(ActivationGrant(enabled=True, receipt_id="grant-1"))
    assert RuntimeAdapter(activation_store, fake_launcher).start("cmd-2", "shadow", "wrong").accepted is False
    assert fake_launcher.calls == []
```

- [ ] **Step 2: Run daemon tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/ops/test_services.py tests/platform/ops/test_supervisor.py -q`

Expected: FAIL because daemon lifecycle and service ports are absent.

- [ ] **Step 3: Implement lifecycle without a Windows service**

When runtime-start authority is true, the confirmed Start command launches one
direct `uv run --locked vesper-ops-daemon` process with state root, requested
mode, activation receipt ID, and start nonce. When false, capability reason is
`Runtime start is not activated or authorized.` The daemon writes heartbeat,
health, and clean-stop records and never creates a Windows service or task.
Gateway capabilities enable only after matching activation, authority receipt,
and a current health probe. Tests use fake launchers and start no real daemon.

```python
def start(self, command_id: SafeId, mode: Literal["shadow", "paper"], activation_receipt_id: SafeId | None) -> RuntimeReceipt:
    grant = self._activation_store.validated_grant(ActivationCapability.RUNTIME_START)
    if not grant.enabled or grant.receipt_id != activation_receipt_id:
        return RuntimeReceipt.rejected(command_id, "activation-receipt-mismatch")
    return self._launcher.start_once(command_id, mode, activation_receipt_id)
```

- [ ] **Step 4: Run daemon tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/ops/test_services.py tests/platform/ops/test_supervisor.py -q`

Expected: PASS with fake process and service adapters.

- [ ] **Step 5: Commit**

```powershell
git add -- 'vesper/platform/ops/services.py' 'vesper/platform/ops/supervisor.py' 'vesper/platform/ops/cli.py' 'pyproject.toml' 'uv.lock' 'vesper/platform/tui/command_ports.py' 'vesper/platform/tui/command_registry.py' 'vesper/platform/tui/gateway.py' 'tests/platform/ops/test_services.py' 'tests/platform/ops/test_supervisor.py'
git commit -m "feat(ops): run governed operations daemon"
```

### Task 6: Enforce model candidate retention

**Files:**
- Create: `vesper/platform/tui/candidate_retention.py`
- Create: `tests/platform/tui/test_candidate_retention.py`

**Interfaces:**
- Produces `CandidateRetentionService.plan(now_utc) -> CandidateRetentionPlan`.
- Produces `CandidateRetentionService.apply(plan_hash, activation_store,
  authority_receipts) -> CandidateRetentionReceipt`; no caller-supplied enabled
  boolean or unrelated authority object can bypass the validated store grant.
- Failed/rejected candidate files expire after 30 days; passed/unselected files expire after 90 days; active/rollback files and all metrics/evidence/lineage are permanent.

```python
class CandidateRetentionService:
    def plan(self, now_utc: datetime) -> CandidateRetentionPlan: ...
    def apply(self, plan_hash: Sha256Hex, activation_store: OperationsActivationStore, authority_receipts: AuthorityReceiptStore) -> CandidateRetentionReceipt: ...

class AuthorityReceiptStore:
    def require_candidate_deletion(self, receipt_id: NonEmptyStr, approved_root: Path, plan_hash: Sha256Hex) -> AuthorityReceipt: ...
```

- [ ] **Step 1: Write boundary, protected-root, and low-disk tests**

Use a temporary candidate root. Test one second before and at each retention
boundary, immutable active and rollback IDs, permanent metadata, symlink escape,
path traversal, unknown status, mismatched plan hash, changed file after plan,
protected-root overlap, disabled authority, missing/mismatched authority receipt,
and root mismatch. Low disk must pause candidate training and must not shorten
retention. A disabled store grant must make zero file deletions.

```python
@pytest.mark.parametrize("receipt_id", [None, "wrong-receipt"])
def test_candidate_delete_rejects_missing_or_mismatched_grant(receipt_id, service, activation_store, receipt_store, delete_spy) -> None:
    grant = ActivationGrant() if receipt_id is None else ActivationGrant(enabled=True, receipt_id=receipt_id)
    activation_store.set_candidate_deletion(grant)
    receipt = service.apply(PLAN_HASH, activation_store, receipt_store)
    assert receipt.accepted is False
    assert delete_spy.calls == []


def test_candidate_delete_receipt_binds_root_and_plan(service, enabled_store, receipt_store, delete_spy) -> None:
    receipt_store.add_candidate_deletion("grant-1", approved_root=OTHER_ROOT, plan_hash=PLAN_HASH)
    assert service.apply(PLAN_HASH, enabled_store, receipt_store).accepted is False
    receipt_store.replace_candidate_deletion("grant-1", approved_root=CANDIDATE_ROOT, plan_hash=OTHER_HASH)
    assert service.apply(PLAN_HASH, enabled_store, receipt_store).accepted is False
    assert delete_spy.calls == []
```

- [ ] **Step 2: Run tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_candidate_retention.py -q`

Expected: FAIL because retention is absent.

- [ ] **Step 3: Implement plan-before-delete retention**

Require a controller-owned manifest binding candidate ID, status, created time,
files, hashes, active ID, and rollback ID. Resolve every path below an approved
candidate-output root that cannot overlap the repository, Massive data, or model
research. Write an immutable deletion manifest, verify file hashes again, delete
only listed candidate binaries, and retain metrics/evidence/lineage records.
`apply` reads only `activation_store.current().candidate_deletion`, requires its
enabled grant and matching receipt ID, then calls
`authority_receipts.require_candidate_deletion` with the exact resolved root and
plan hash before the first filesystem mutation. No production
caller or scheduler is registered in this plan; only temporary-root tests use an
enabled validated store grant.

```python
grant = activation_store.validated_grant(ActivationCapability.CANDIDATE_DELETION)
if not grant.enabled:
    return CandidateRetentionReceipt.rejected("activation-disabled")
authority_receipts.require_candidate_deletion(grant.receipt_id, self.root, plan_hash)
self._apply_verified_plan(plan_hash)
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_candidate_retention.py -q`

Expected: PASS with no access outside the temporary candidate root and zero
deletions through the default disabled authority.

- [ ] **Step 5: Commit**

```powershell
git add -- 'vesper/platform/tui/candidate_retention.py' 'tests/platform/tui/test_candidate_retention.py'
git commit -m "feat(tui): enforce candidate artifact retention"
```

### Task 7: Send generic Windows notifications

**Files:**
- Create: `vesper/platform/tui/notifications.py`
- Create: `tests/platform/tui/test_notifications.py`
- Modify: `vesper/platform/tui/command_registry.py`

**Interfaces:**
- Produces protocol `NotificationPort.send_attention(alert_id)` so a private
  phone adapter can be added without changing alert policy; no remote adapter is
  implemented here.
- Produces `WindowsNotificationPort.send_attention(alert_id) -> NotificationReceipt`.
- Uses AppUserModelID `Vesper.V20.TUI` and launch argument `--alert-id {alert_id}`.

```python
class NotificationPort(Protocol):
    def send_attention(self, alert_id: SafeId) -> NotificationReceipt: ...

class WindowsNotificationPort:
    def send_attention(self, alert_id: SafeId) -> NotificationReceipt: ...
```

- [ ] **Step 1: Write content, routing, and failure tests**

Assert title/body expose only `V20 needs attention`, alert IDs match the safe ID
regex, XML escaping is correct, clicking launches the TUI with only the alert
ID, unlock is still required, duplicate active alerts coalesce, and notification
failure becomes System health without crashing the supervisor.

```python
def test_notification_contains_only_generic_text(port, winrt_spy) -> None:
    port.send_attention("alert-1")
    assert winrt_spy.visible_text == ["V20 needs attention"]
```

- [ ] **Step 2: Run tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_notifications.py -q`

Expected: FAIL because notifications are absent.

- [ ] **Step 3: Implement WinRT toast construction**

Build the toast XML with `XmlDocument`, create a notifier for the fixed AppID,
and show `ToastNotification`. Do not add portfolio, account, stock, order, model,
or agent text. Send only when no authenticated TUI client is connected.

```python
def send_attention(self, alert_id: SafeId) -> NotificationReceipt:
    if self._sessions.has_authenticated_client():
        return NotificationReceipt.suppressed(alert_id)
    return self._show_xml(build_toast_xml("V20 needs attention", alert_id))
```

- [ ] **Step 4: Run tests, verify GREEN, and perform one manual local notification check**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_notifications.py -q`

The automated test mocks WinRT. The manual check uses a generated safe alert ID,
confirms generic visible text, clicks it, and confirms the locked TUI opens at
that alert after unlock.

- [ ] **Step 5: Commit**

```powershell
git add -- 'vesper/platform/tui/notifications.py' 'tests/platform/tui/test_notifications.py' 'vesper/platform/tui/command_registry.py'
git commit -m "feat(tui): add private generic notifications"
```

### Task 8: Add encrypted backup and staged restore

**Files:**
- Create: `vesper/platform/tui/backup.py`
- Modify: `vesper/platform/tui/command_ports.py`
- Modify: `vesper/platform/tui/command_registry.py`
- Create: `tests/platform/tui/test_backup.py`

**Interfaces:**

```python
class BackupService:
    def create(self, destination: Path) -> BackupManifest: ...
    def preview_restore(self, archive: Path) -> RestorePreview: ...
    def restore(self, archive: Path, confirmation: RestoreConfirmation) -> RestoreReceipt: ...

class BackupCommandPort(Protocol):
    def create(self, command_id: SafeId, destination: Path) -> BackupManifest: ...
    def restore(self, command_id: SafeId, archive: Path, preview_hash: Sha256Hex, safety_backup_receipt_id: SafeId, confirmation: RestoreConfirmation) -> RestoreReceipt: ...
```

- [ ] **Step 1: Write encrypted archive and staged-restore tests**

```python
def test_restore_replaces_nothing_without_stopped_runtime_and_safety_backup(service, replace_spy) -> None:
    confirmation = RestoreConfirmation(preview_hash=PREVIEW_HASH, first=True, second=True)
    receipt = service.restore(ARCHIVE, confirmation)
    assert receipt.accepted is False
    assert replace_spy.calls == []

def test_backup_excludes_secrets_and_protected_data(service, destination) -> None:
    manifest = service.create(destination)
    assert all(".env" not in path for path in manifest.paths)
    assert all("vesper/data/massive" not in path for path in manifest.paths)
    assert b"PK\x03\x04" not in destination.read_bytes()
```

- [ ] **Step 2: Run backup tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_backup.py -q`

Expected: FAIL because backup and restore are absent.

- [ ] **Step 3: Implement deterministic DPAPI archive and restore transaction**

```python
def restore(self, archive: Path, confirmation: RestoreConfirmation) -> RestoreReceipt:
    self._runtime.require_exactly_stopped()
    verified = self._decrypt_validate_archive(archive)
    preview = self._build_complete_preview(verified)
    self._require_preview_hash(preview, confirmation.preview_hash)
    safety = self.create(self._safety_destination())
    self._verify_safety_backup(safety)
    self._recheck_sources(verified, preview)
    self._require_double_confirmation(confirmation, preview.sha256)
    try:
        self._replace_allowlisted_paths(verified, preview)
        self._verify_restored_state(preview)
    except Exception:
        self._rollback_from_safety_backup(safety)
        raise
    return RestoreReceipt.completed(preview.sha256, safety.receipt_id)
```

Archive creation uses sorted paths, normalized timestamps, entry sizes and
SHA-256 in a JSON manifest, current-user `CryptProtectData`, and atomic replace.
Validation rejects absolute paths, drive prefixes, `..`, symlinks, duplicates,
credentials, caches, and protected data. Before replacement failure changes
zero target paths; post-replacement failure rolls back from the safety backup.

- [ ] **Step 4: Run backup tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_backup.py -q`

Expected: PASS including corrupt, wrong-user, traversal, and rollback cases.

- [ ] **Step 5: Commit**

```powershell
git add -- 'vesper/platform/tui/backup.py' 'vesper/platform/tui/command_ports.py' 'vesper/platform/tui/command_registry.py' 'tests/platform/tui/test_backup.py'
git commit -m "feat(tui): add encrypted backup and restore"
```

### Task 9: Add the encrypted snapshot cache

**Files:**
- Create: `vesper/platform/tui/snapshot_cache.py`
- Modify: `vesper/platform/tui/gateway.py`
- Create: `tests/platform/tui/test_snapshot_cache.py`

**Interfaces:**

```python
class SnapshotCache:
    def write(self, snapshot: ConsoleSnapshot) -> CacheReceipt: ...
    def read_after_unlock(self) -> CachedSnapshot | None: ...
```

- [ ] **Step 1: Write locked, stale-cache, and fresh-replacement tests**

```python
def test_cache_is_hidden_until_unlock_and_never_authorizes(cache, gateway) -> None:
    cache.write(console_snapshot(command_specs=COMMAND_SPECS))
    assert gateway.snapshot_while_locked() is None
    cached = gateway.unlock(PASSWORD).snapshot
    assert cached.label == "STALE CACHE"
    assert cached.command_specs == ()
    assert all(cap.state is CapabilityState.DISABLED for cap in cached.capabilities)
```

- [ ] **Step 2: Run cache tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_snapshot_cache.py -q`

Expected: FAIL because encrypted cache support is absent.

- [ ] **Step 3: Implement current-user encrypted cache projection**

```python
def read_after_unlock(self) -> CachedSnapshot | None:
    plaintext = win32crypt.CryptUnprotectData(self._path.read_bytes(), None, None, None, 0)[1]
    snapshot = ConsoleSnapshot.model_validate_json(plaintext)
    return CachedSnapshot.from_snapshot(snapshot, label="STALE CACHE", command_specs=(), disable_all=True)
```

Write cache bytes atomically with current-user DPAPI. A fresh gateway snapshot
atomically replaces the cached projection before command specs or capabilities
can become enabled.

- [ ] **Step 4: Run cache tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_snapshot_cache.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- 'vesper/platform/tui/snapshot_cache.py' 'vesper/platform/tui/gateway.py' 'tests/platform/tui/test_snapshot_cache.py'
git commit -m "feat(tui): add encrypted snapshot cache"
```

### Task 10: Add recovery-mode inspection

**Files:**
- Create: `vesper/platform/tui/recovery.py`
- Modify: `vesper/platform/tui/gateway.py`
- Create: `tests/platform/tui/test_recovery.py`

**Interfaces:**

```python
class RecoveryService:
    def inspect(self) -> RecoveryReport: ...
```

- [ ] **Step 1: Write unclean-stop recovery tests**

```python
def test_unclean_stop_blocks_broker_actions_until_reconciled(service) -> None:
    report = service.inspect()
    assert report.mode == "recovery"
    assert report.broker_actions_enabled is False
    assert set(report.checks) == {"journal-chain", "state-version", "active-work", "model-reference", "portfolio-source", "broker-reconciliation"}
```

- [ ] **Step 2: Run recovery tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_recovery.py -q`

Expected: FAIL because recovery inspection is absent.

- [ ] **Step 3: Implement fail-closed recovery report**

```python
def inspect(self) -> RecoveryReport:
    checks = self._run_exact_checks()
    matched = checks["broker-reconciliation"].state == "matched"
    return RecoveryReport(mode="recovery", checks=checks, broker_actions_enabled=False, resume_requires_confirmation=matched)
```

The gateway exposes the report as read state. Only a future approved broker port
plus operator resume confirmation may leave Recovery Mode.

- [ ] **Step 4: Run recovery tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_recovery.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- 'vesper/platform/tui/recovery.py' 'vesper/platform/tui/gateway.py' 'tests/platform/tui/test_recovery.py'
git commit -m "feat(tui): add fail-closed recovery mode"
```

### Task 11: Compress raw logs without deleting history

**Files:**
- Create: `vesper/platform/tui/retention.py`
- Create: `tests/platform/tui/test_retention.py`

**Interfaces:**

```python
class HistoryRetentionService:
    def apply(self, now_utc: datetime) -> HistoryRetentionReceipt: ...
```

- [ ] **Step 1: Write permanent-history and 30-day boundary tests**

```python
def test_retention_removes_only_verified_raw_log_copy(service, raw_log, now_utc) -> None:
    receipt = service.apply(now_utc)
    assert receipt.compressed_sha256
    assert gzip.decompress(receipt.compressed_path.read_bytes()) == ORIGINAL_BYTES
    assert not raw_log.exists()
    assert service.permanent_history_rows() == ORIGINAL_HISTORY_ROWS
```

- [ ] **Step 2: Run retention tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_retention.py -q`

Expected: FAIL because history retention is absent.

- [ ] **Step 3: Implement verified deterministic compression**

```python
compressed = deterministic_gzip(raw_bytes)
atomic_write(compressed_path, compressed)
if gzip.decompress(compressed_path.read_bytes()) != raw_bytes:
    raise RetentionError("decompression-mismatch")
raw_path.unlink()
return HistoryRetentionReceipt(original_sha256=sha256(raw_bytes), compressed_sha256=sha256(compressed))
```

Only raw logs at or beyond 30 days enter this path. Portfolio, order, approval,
memory, agent, compressed-log, metrics, evidence, and lineage history is never
deleted.

- [ ] **Step 4: Run retention tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_retention.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- 'vesper/platform/tui/retention.py' 'tests/platform/tui/test_retention.py'
git commit -m "feat(tui): compress raw logs safely"
```

### Task 12: Enforce safe local code maintenance

**Files:**
- Create: `vesper/platform/tui/maintenance.py`
- Create: `vesper/platform/tui/git_port.py`
- Modify: `vesper/platform/tui/command_ports.py`
- Modify: `vesper/platform/tui/command_registry.py`
- Create: `tests/platform/tui/test_maintenance.py`
- Create: `tests/platform/tui/test_git_port.py`

**Interfaces:**
- Produces `MaintenancePolicy.evaluate(candidate) -> MaintenanceDecision`.
- Produces `LocalGitPort.create_worktree`, `verify`, `merge_no_ff`, `revert`, and `status`.
- Produces a separate confirmed `push` method that is never called automatically.
- Produces `SourceControlCommandPort.push(command_id, expected_revision,
  confirmation)`; construction does not enable push, and automatic merge uses
  the separate receipt-bound `automatic_merge` grant.

```python
class MaintenancePolicy:
    def evaluate(self, candidate: MaintenanceCandidate) -> MaintenanceDecision: ...

class LocalGitPort:
    def create_worktree(self, request: WorktreeRequest) -> GitReceipt: ...
    def verify(self, request: VerificationRequest) -> GitReceipt: ...
    def merge_no_ff(self, request: MergeRequest) -> GitReceipt: ...
    def revert(self, commit: GitRevision) -> GitReceipt: ...
    def status(self) -> RepositoryStatus: ...
    def push(self, expected_revision: GitRevision, confirmation: ConfirmationProof) -> GitReceipt: ...

class SourceControlCommandPort(Protocol):
    def push(self, command_id: SafeId, expected_revision: GitRevision, confirmation: ConfirmationProof) -> GitReceipt: ...
```

- [ ] **Step 1: Write policy and disposable-repository tests**

Allow only explicit low-risk globs configured in policy. Always forbid broker,
orders, portfolio, risk, models, training policy, scheduler, credentials,
protected data, `AGENTS.md`, dependency files, CI, and broad architecture. Assert
dirty main, unexpected revision, missing review, failed focused/broad tests,
failed formatting/static checks, missing rollback commit, or held merge lock
rejects merge. Assert a post-merge failed check creates one revert. Assert no
automatic path invokes push.
Assert a disabled `automatic_merge` store grant blocks merge even in a clean
disposable main and when every policy check passes. Assert an enabled grant with
a missing or mismatched receipt ID makes zero Git mutation calls. Assert the confirmed push port is disabled
until injected and never shares the automatic-merge activation grant.

```python
def test_auto_merge_requires_validated_store_grant(clean_candidate, activation_store, git_spy) -> None:
    activation_store.set_automatic_merge(ActivationGrant())
    assert MaintenancePolicy(activation_store).evaluate(clean_candidate).allowed is False
    activation_store.set_automatic_merge(ActivationGrant(enabled=True, receipt_id="wrong"))
    assert MaintenancePolicy(activation_store).evaluate(clean_candidate).allowed is False
    assert git_spy.mutations == []
```

- [ ] **Step 2: Run tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_maintenance.py tests/platform/tui/test_git_port.py -q`

Expected: FAIL because maintenance is absent.

- [ ] **Step 3: Implement direct Git argv and path validation**

Use direct subprocess argument lists with five-minute bounded test commands.
Resolve every candidate path below the worktree, reject symlinks leaving it,
bind review to exact diff hash, and acquire one LocalAppData merge lock. Use a
no-fast-forward merge so rollback has one target commit. Never clear or reset a
dirty worktree.

Wire the confirmed push adapter through the command registry only when its
health probe passes. Automatic maintenance additionally requires
the enabled `activation_store.validated_grant(ActivationCapability.AUTOMATIC_MERGE)`
and its matching receipt;
adapter availability and a clean main are necessary but insufficient.

```python
grant = self._activation_store.validated_grant(ActivationCapability.AUTOMATIC_MERGE)
if not grant.enabled:
    return MaintenanceDecision.reject("automatic-merge-disabled")
```

- [ ] **Step 4: Keep current main disabled**

The System capability reason must read `Automatic merge is disabled because
main is not clean.` while current status is dirty. No cleanup command is offered
by this service.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_maintenance.py tests/platform/tui/test_git_port.py -q`

Expected: PASS in disposable repositories with zero network access.

- [ ] **Step 6: Commit**

```powershell
git add -- 'vesper/platform/tui/maintenance.py' 'vesper/platform/tui/git_port.py' 'vesper/platform/tui/command_ports.py' 'vesper/platform/tui/command_registry.py' 'tests/platform/tui/test_maintenance.py' 'tests/platform/tui/test_git_port.py'
git commit -m "feat(tui): govern local code maintenance"
```

### Task 13: Package, measure, and verify the complete console

**Files:**
- Create: `scripts/build-tui.ps1`
- Create: `scripts/install-tui-shortcut.ps1`
- Create: `scripts/verify-tui.ps1`
- Create: `tests/platform/tui/test_tui_scripts.py`
- Modify: `TUI testing/ratatui-console/README.md`
- Create: `TUI testing/results/FINAL_VERIFICATION.md`
- Create: `TUI testing/results/performance.json`

**Interfaces:**
- Produces `dist/tui/vesper-ratatui-console.exe` and a checksum receipt.
- Produces optional current-user Start Menu shortcut with AppUserModelID `Vesper.V20.TUI`.
- Produces fresh test and performance receipts.

- [ ] **Step 1: Write PowerShell script contract tests**

Parse scripts without executing installation. Assert build uses locked Cargo and
uv environments, output stays below `dist/tui`, shortcut install is explicit and
current-user only, no administrator action is requested, and verification writes
exact command/exit/duration receipts.

```python
def test_verify_script_is_locked_and_isolated() -> None:
    text = Path("scripts/verify-tui.ps1").read_text(encoding="utf-8")
    assert "uv run --locked python -m pytest" in text
    assert "--basetemp C:\\tmp\\v20-tui-operations-pytest" in text
    assert "cache_dir=C:\\tmp\\v20-tui-operations-cache" in text
```

- [ ] **Step 2: Run script contract tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_tui_scripts.py -q`

Expected: FAIL because the scripts are absent.

- [ ] **Step 3: Implement locked release build**

`build-tui.ps1` runs Python focused tests, Cargo fmt/Clippy/tests, Cargo release
build, copies only the executable and README, and writes SHA-256 plus tool
versions. It does not package `.env`, state, credentials, target directories, or
Python caches.

Every pytest invocation inside `build-tui.ps1` and `verify-tui.ps1` must set
`TEMP=C:\tmp\v20-tui-operations-temp` and
`TMP=C:\tmp\v20-tui-operations-temp`, and pass exactly
`--basetemp C:\tmp\v20-tui-operations-pytest -o
cache_dir=C:\tmp\v20-tui-operations-cache` before test paths.

```powershell
$env:TEMP='C:\tmp\v20-tui-operations-temp'
$env:TMP='C:\tmp\v20-tui-operations-temp'
uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui tests/platform/ops -q
cargo build --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --release --locked
```

- [ ] **Step 4: Run script contract tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui/test_tui_scripts.py -q`

Expected: PASS.

- [ ] **Step 5: Run the complete focused and broader gates**

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform/tui tests/platform/ops -q`

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' tests/platform tests/test_risk.py tests/test_shadow_evidence.py -q`

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-operations-pytest' -o cache_dir='C:\tmp\v20-tui-operations-cache' -q`

Run: `cargo fmt --manifest-path "TUI testing/ratatui-console/Cargo.toml" -- --check`

Run: `cargo clippy --manifest-path "TUI testing/ratatui-console/Cargo.toml" --all-targets --locked -- -D warnings`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --locked`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --release --locked`

Run: `$env:TEMP='C:\tmp\v20-tui-operations-temp'; $env:TMP='C:\tmp\v20-tui-operations-temp'; & scripts/verify-tui.ps1`

Expected: every required command exits zero; failures remain recorded and block
completion.

- [ ] **Step 6: Measure approved performance targets**

Record cached unlock-to-first-screen, event-to-visible latency, input latency,
idle CPU, continuous memory growth, 10,000-row filter/navigation, long chat
streaming, and clean process shutdown. Use at least 10 warmups and 100 measured
samples where applicable. Record median, p95, max, environment, build hash, and
raw samples. Do not subtract Python, broker, data, or model latency from their
own measurements; label each source.

Measure cached unlock from successful auth result to first `STALE CACHE` frame
using the encrypted cache built in Task 9. Measure input from Crossterm event
receipt to changed backend cell with the 10 ms poll from foundation; report poll,
dispatch, reduce, and draw components separately. Sample process CPU once per
second for 10 idle minutes after warmup. Measure retained memory from identical
heap/process counters at the start and end of a one-hour synthetic stream.
Instrument dirty-panel renderer calls and backend cell writes so the one-panel
redraw gate proves scope, not merely elapsed time.

Required gates: cached screen at or below 1 second, normal event visibility p95
at or below 250 ms, input p95 at or below 50 ms, idle TUI CPU p95 below 1 percent,
less than 10 MiB retained-memory growth during a one-hour synthetic stream, no
full-screen redraw for a one-panel event, responsive 10,000-row navigation, and
no orphan TUI or gateway process after stop. A miss is reported and blocks the
performance gate; thresholds are not changed after measurement.

- [ ] **Step 7: Run manual acceptance without financial side effects**

Verify password on every open, viewer Take Control, all ten screens, both themes,
three text sizes, keyboard/mouse parity, unavailable controls, generic Windows
notification, TUI close while fake daemon continues, safe shutdown preparation,
backup/restore against temporary state, and dirty-main auto-merge block. Do not
activate broker, Live, real training, real scheduler, or automatic merge.

- [ ] **Step 8: Reconcile every design acceptance criterion**

Write one row per criterion with `PASS`, `BLOCKED`, or `NOT ACTIVATED`, exact
test/receipt/file evidence, and reason. `BLOCKED` prevents completion;
`NOT ACTIVATED` is valid only for separately gated real-world capabilities whose
code path is disabled and tested.

- [ ] **Step 9: Commit**

```powershell
git add -- 'scripts/build-tui.ps1' 'scripts/install-tui-shortcut.ps1' 'scripts/verify-tui.ps1' 'tests/platform/tui/test_tui_scripts.py' 'TUI testing/ratatui-console/README.md' 'TUI testing/results/FINAL_VERIFICATION.md' 'TUI testing/results/performance.json'
git commit -m "release(tui): verify V20 operations console"
```

## Phase acceptance

- Per-agent human chats stream and persist separately.
- Raw chats survive automatic context compression.
- V20 Core Memory stays within 2,000 words and all changes are reversible.
- Quiet Mode and continuous-work decisions are deterministic and resource-bound.
- Runtime start, continuous work, daily curation, candidate training, candidate
  deletion, and automatic merge remain independently disabled without their
  exact authority receipts.
- No candidate training runs without an approved port.
- Notifications are generic and unlock remains required.
- DPAPI backup and staged restore pass corruption and traversal tests.
- Recovery blocks broker work until reconciliation and confirmation.
- Automatic maintenance rejects dirty main and all forbidden scopes.
- Final Python, Rust, broader, manual, and performance evidence is recorded.
- Real financial/scheduler/training/merge activation remains a separate authority event.
