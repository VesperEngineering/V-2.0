# V20 Ratatui Continuous Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete continuous governed agents, separate chats, bounded Qwen context, V20-only working memory, notifications, backup/recovery, safe local code maintenance, packaging, and final performance verification.

**Architecture:** A controller-owned operations daemon may outlive the TUI and runs only capabilities explicitly enabled by its policy. Conversation, working-memory, backup, notification, and maintenance services expose typed ports to the gateway. Rust remains a client. Sensitive or unavailable services remain disabled until their runtime prerequisites and authority gates pass.

**Tech Stack:** Earlier phase stack plus Python WinRT 3.2.1 notifications, Windows DPAPI through pywin32, SQLite, Obsidian-compatible Markdown, Git worktrees, PowerShell packaging, and Windows Task-free process supervision.

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
`-- test_snapshot_cache.py

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

Run: `uv run --locked python -m pytest tests/platform/test_dependencies.py -q`

Expected: FAIL because pins are absent.

- [ ] **Step 3: Add exact Windows markers and refresh the lock**

Run `uv lock` after adding all three dependency strings.

- [ ] **Step 4: Run the test and verify GREEN**

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `build(tui): pin Windows notification support`

### Task 2: Store separate agent conversations and bounded summaries

**Files:**
- Create: `vesper/platform/tui/conversations.py`
- Create: `vesper/platform/tui/compression.py`
- Create: `tests/platform/tui/test_conversations.py`
- Create: `tests/platform/tui/test_compression.py`
- Create: `TUI testing/ratatui-console/src/chat.rs`
- Create: `TUI testing/ratatui-console/tests/chat.rs`

**Interfaces:**
- Produces `ConversationStore.start_message`, `append_chunk`, `complete`, `interrupt`, and `history`.
- Produces statuses `draft`, `complete`, and `interrupted`.
- Produces `CompressionPolicy.should_compress(prompt_tokens) -> bool`.
- Produces `ContextCompressor.build(agent_id, objective) -> CompressedContext`.

- [ ] **Step 1: Write append, stream, interruption, and compression tests**

Assert each agent has a separate thread; only human/agent roles exist; chunks
append in sequence; completed output cannot change; disconnect leaves draft as
interrupted; raw text survives compression; compression starts at
`floor(MAX_INPUT_TOKENS * 0.80)`; and the summary retains objective, current
state, unresolved decisions, approvals, evidence IDs, errors, blockers,
applicable rules, core-memory IDs, and raw-message pointers.

- [ ] **Step 2: Run Python and Rust chat tests and verify RED**

Expected: FAIL because chat storage is absent.

- [ ] **Step 3: Implement the SQLite chat ledger**

Use immutable message rows plus ordered chunk rows. Store agent ID, role,
created/completed timestamps, validation state, token counts, and context-summary
lineage. Never store private chain-of-thought fields. `complete` requires the
controller's validation receipt ID.

- [ ] **Step 4: Implement per-agent hidden chat UI**

Open chat only from an agent card or explicit agent selector. Render streamed
content as `DRAFT`; replace with `COMPLETE` only on a complete event; retain
`INTERRUPTED` output in history. `Enter` sends only when input owns focus.

- [ ] **Step 5: Run tests and verify GREEN**

Expected: PASS including reopen and 64K-context boundary cases.

- [ ] **Step 6: Commit**

Commit: `feat(tui): preserve separate agent conversations`

### Task 3: Implement V20-only 2,000-word working memory

**Files:**
- Create: `vesper/platform/tui/working_memory.py`
- Create: `tests/platform/tui/test_working_memory.py`
- Modify: `TUI testing/ratatui-console/src/screens/memory.rs`

**Interfaces:**
- Produces `WorkingMemoryStore.propose`, `curate`, `core`, `archive`, `history`, and `rollback`.
- Produces `MemoryValueScore` from evidence, usefulness, reuse, relevance, age, and safety rarity.
- Uses default vault `%USERPROFILE%\Documents\V20 Qwen Vault`.

- [ ] **Step 1: Write scope, limit, archive, and authority tests**

Reject non-V20 content, secrets, task progress, temporary blockers, unsupported
claims, and any write to repository `knowledge/`. Count words with Unicode word
boundaries and require core count `<= 2000`. Assert stronger candidates may
replace lower-value items, rare safety facts receive a protected score floor,
demoted items move to archive, every mutation records evidence/reason, and
rollback restores the prior core exactly. The contract has no manual pin field.

- [ ] **Step 2: Run tests and verify RED**

Expected: FAIL because working memory is absent.

- [ ] **Step 3: Implement Obsidian-compatible files plus a SQLite ledger**

Write `Core Memory.md`, `Archive/{memory_id}.md`, and `History/{change_id}.md`
atomically. Front matter contains ID, status, created/updated UTC, evidence IDs,
score components, supersedes, and content hash. Core rules and `AGENTS.md` are
read-only inputs and do not count toward 2,000 words.

- [ ] **Step 4: Implement automatic curation**

Curate after validated completed work and once daily. Choose the highest-value
set within 2,000 words using deterministic score then memory ID tie-break. Qwen
may propose text; the controller validates scope/evidence and makes the final
file change. This store never calls `knowledge-sync` and never marks repository
knowledge approved.

- [ ] **Step 5: Run tests and verify GREEN**

Expected: PASS including crash between file and ledger update with repair on
reopen.

- [ ] **Step 6: Commit**

Commit: `feat(tui): add bounded V20 working memory`

### Task 4: Add continuous governed operations and Quiet Mode

**Files:**
- Create: `vesper/platform/ops/__init__.py`
- Create: `vesper/platform/ops/policy.py`
- Create: `vesper/platform/ops/training.py`
- Create: `vesper/platform/ops/services.py`
- Create: `vesper/platform/ops/supervisor.py`
- Create: `vesper/platform/ops/cli.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `tests/platform/ops/test_policy.py`
- Create: `tests/platform/ops/test_training.py`
- Create: `tests/platform/ops/test_services.py`
- Create: `tests/platform/ops/test_supervisor.py`

**Interfaces:**
- Produces script `vesper-ops-daemon`.
- Produces `OperationsPolicy.next_action(state, now) -> ActionDecision`.
- Produces `OperationsSupervisor.run(stop_event) -> None`.
- Produces `QwenWorkPort.available()` and `run_one(work_item)`.
- Produces `CandidateTrainingPort.available()` and `train_and_evaluate(request)`.
- Produces `ServiceSupervisor.handle_failure(service_id)` with one automatic restart.

- [ ] **Step 1: Write deterministic priority and quiet-mode tests**

Test priority order: incident, approval, portfolio, operator command, normal
queue, research backlog. Test Quiet Mode at 18:59, 19:00, 07:59, 08:00 ET,
weekends, and DST transitions. Test lower GPU budget and longer pause in quiet
mode, temperature/memory/disk/error rest, global/per-agent queue caps, duplicate
merge, backlog overflow, one Qwen lease, one safe restart, and alert after a
failed restart. A broker-position mismatch must idempotently enqueue one urgent
Reconciliation Agent task owned by the source adapter and block new order or
rebalance admission while other work continues. When resources allow and an
approved training port is available, one candidate request may run; it must bind
the approved model family, strategy, features, data identity, evaluation
contract, and artifact root.

- [ ] **Step 2: Run operations tests and verify RED**

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

- [ ] **Step 4: Implement daemon lifecycle without a Windows service**

The confirmed Start command launches one direct `uv run --locked
vesper-ops-daemon` process with a state-root argument and a start nonce stored in
the command receipt. A named single-instance mutex blocks duplicates. The daemon
writes heartbeat, health, and clean-stop records. It continues when the TUI and
gateway close. Prepare for PC Shutdown stops admission, finishes or pauses one
bounded unit, checkpoints chats/journals/state, and reports `SAFE TO SHUT DOWN`.

- [ ] **Step 5: Run tests and verify GREEN**

Expected: PASS with fake Qwen, fake queues, fake resources, and fake training.

- [ ] **Step 6: Commit**

Commit: `feat(ops): add bounded continuous supervisor`

### Task 5: Enforce model candidate retention

**Files:**
- Create: `vesper/platform/tui/candidate_retention.py`
- Create: `tests/platform/tui/test_candidate_retention.py`

**Interfaces:**
- Produces `CandidateRetentionService.plan(now) -> CandidateRetentionPlan`.
- Produces `CandidateRetentionService.apply(plan_hash) -> CandidateRetentionReceipt`.
- Failed/rejected candidate files expire after 30 days; passed/unselected files expire after 90 days; active/rollback files and all metrics/evidence/lineage are permanent.

- [ ] **Step 1: Write boundary, protected-root, and low-disk tests**

Use a temporary candidate root. Test one second before and at each retention
boundary, immutable active and rollback IDs, permanent metadata, symlink escape,
path traversal, unknown status, mismatched plan hash, changed file after plan,
and protected-root overlap. Low disk must pause candidate training and must not
shorten retention.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --locked python -m pytest tests/platform/tui/test_candidate_retention.py -q`

Expected: FAIL because retention is absent.

- [ ] **Step 3: Implement plan-before-delete retention**

Require a controller-owned manifest binding candidate ID, status, created time,
files, hashes, active ID, and rollback ID. Resolve every path below an approved
candidate-output root that cannot overlap the repository, Massive data, or model
research. Write an immutable deletion manifest, verify file hashes again, delete
only listed candidate binaries, and retain metrics/evidence/lineage records.

- [ ] **Step 4: Run tests and verify GREEN**

Expected: PASS with no access outside the temporary candidate root.

- [ ] **Step 5: Commit**

Commit: `feat(tui): enforce candidate artifact retention`

### Task 6: Send generic Windows notifications

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

- [ ] **Step 1: Write content, routing, and failure tests**

Assert title/body expose only `V20 needs attention`, alert IDs match the safe ID
regex, XML escaping is correct, clicking launches the TUI with only the alert
ID, unlock is still required, duplicate active alerts coalesce, and notification
failure becomes System health without crashing the supervisor.

- [ ] **Step 2: Run tests and verify RED**

Expected: FAIL because notifications are absent.

- [ ] **Step 3: Implement WinRT toast construction**

Build the toast XML with `XmlDocument`, create a notifier for the fixed AppID,
and show `ToastNotification`. Do not add portfolio, account, stock, order, model,
or agent text. Send only when no authenticated TUI client is connected.

- [ ] **Step 4: Run tests and one manual local notification check**

The automated test mocks WinRT. The manual check uses a generated safe alert ID,
confirms generic visible text, clicks it, and confirms the locked TUI opens at
that alert after unlock.

- [ ] **Step 5: Commit**

Commit: `feat(tui): add private generic notifications`

### Task 7: Add DPAPI backup, restore, cache, and recovery

**Files:**
- Create: `vesper/platform/tui/backup.py`
- Create: `vesper/platform/tui/recovery.py`
- Create: `vesper/platform/tui/snapshot_cache.py`
- Create: `vesper/platform/tui/retention.py`
- Create: `tests/platform/tui/test_backup.py`
- Create: `tests/platform/tui/test_recovery.py`
- Create: `tests/platform/tui/test_snapshot_cache.py`
- Create: `tests/platform/tui/test_retention.py`

**Interfaces:**
- Produces `BackupService.create(destination) -> BackupManifest`.
- Produces `BackupService.preview_restore(archive) -> RestorePreview`.
- Produces `BackupService.restore(archive, confirmation) -> RestoreReceipt`.
- Produces `RecoveryService.inspect() -> RecoveryReport`.
- Produces `HistoryRetentionService.apply(now) -> HistoryRetentionReceipt`.
- Produces current-user encrypted last snapshot cache.

- [ ] **Step 1: Write allowlist, encryption, restore, and recovery tests**

Assert backup includes settings, TUI stores, chats, working memory, journals,
receipts, and eligible platform state; excludes `.env`, credential patterns,
broker config values, protected source data, caches, model research, and Massive
data. Assert plaintext ZIP signatures and known fixture text do not appear in
the DPAPI file. Assert restore requires stopped runtime, valid manifest hashes,
exact preview, automatic safety backup, confirmation bound to preview hash, and
post-restore verification.
Assert permanent history is never deleted and raw logs compress only at the
30-day boundary after a successful byte-for-byte decompression check.

- [ ] **Step 2: Run tests and verify RED**

Expected: FAIL because backup/recovery is absent.

- [ ] **Step 3: Implement deterministic archive and current-user DPAPI**

Build a ZIP in memory with sorted paths, normalized timestamps, a JSON manifest,
file sizes, and SHA-256 hashes. Encrypt with `win32crypt.CryptProtectData` using
the current user and no `CRYPTPROTECT_LOCAL_MACHINE`. Write atomically. Decrypt
with `CryptUnprotectData`, validate every entry before extraction, reject
absolute paths, drive prefixes, `..`, symlinks, and duplicate names.

- [ ] **Step 4: Implement staged restore and recovery mode**

Extract to a sibling temporary directory, verify, take a safety backup, then
replace only allowlisted state paths. On unclean stop verify journal chains,
state versions, active work, model references, portfolio-source status, and
broker reconciliation status. Broker actions remain disabled until a future
approved broker port reports matched and the operator confirms resume.

Keep portfolio, order, approval, memory, and agent history permanently. After
30 days, compress raw logs to deterministic gzip, record original/compressed
hashes and byte counts, verify decompression byte-for-byte, then remove only the
verified uncompressed raw-log copy. Never delete compressed history.

- [ ] **Step 5: Run tests and verify GREEN**

Expected: PASS including corrupt, wrong-user simulation, traversal, power-loss,
and rollback cases.

- [ ] **Step 6: Commit**

Commit: `feat(tui): add encrypted recovery and backup`

### Task 8: Enforce safe local code maintenance

**Files:**
- Create: `vesper/platform/tui/maintenance.py`
- Create: `vesper/platform/tui/git_port.py`
- Create: `tests/platform/tui/test_maintenance.py`
- Create: `tests/platform/tui/test_git_port.py`

**Interfaces:**
- Produces `MaintenancePolicy.evaluate(candidate) -> MaintenanceDecision`.
- Produces `LocalGitPort.create_worktree`, `verify`, `merge_no_ff`, `revert`, and `status`.
- Produces a separate confirmed `push` method that is never called automatically.

- [ ] **Step 1: Write policy and disposable-repository tests**

Allow only explicit low-risk globs configured in policy. Always forbid broker,
orders, portfolio, risk, models, training policy, scheduler, credentials,
protected data, `AGENTS.md`, dependency files, CI, and broad architecture. Assert
dirty main, unexpected revision, missing review, failed focused/broad tests,
failed formatting/static checks, missing rollback commit, or held merge lock
rejects merge. Assert a post-merge failed check creates one revert. Assert no
automatic path invokes push.

- [ ] **Step 2: Run tests and verify RED**

Expected: FAIL because maintenance is absent.

- [ ] **Step 3: Implement direct Git argv and path validation**

Use direct subprocess argument lists with five-minute bounded test commands.
Resolve every candidate path below the worktree, reject symlinks leaving it,
bind review to exact diff hash, and acquire one LocalAppData merge lock. Use a
no-fast-forward merge so rollback has one target commit. Never clear or reset a
dirty worktree.

- [ ] **Step 4: Keep current main disabled**

The System capability reason must read `Automatic merge is disabled because
main is not clean.` while current status is dirty. No cleanup command is offered
by this service.

- [ ] **Step 5: Run tests and verify GREEN**

Expected: PASS in disposable repositories with zero network access.

- [ ] **Step 6: Commit**

Commit: `feat(tui): govern local code maintenance`

### Task 9: Package, measure, and verify the complete console

**Files:**
- Create: `scripts/build-tui.ps1`
- Create: `scripts/install-tui-shortcut.ps1`
- Create: `scripts/verify-tui.ps1`
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

- [ ] **Step 2: Implement locked release build**

`build-tui.ps1` runs Python focused tests, Cargo fmt/Clippy/tests, Cargo release
build, copies only the executable and README, and writes SHA-256 plus tool
versions. It does not package `.env`, state, credentials, target directories, or
Python caches.

- [ ] **Step 3: Run the complete focused and broader gates**

Run: `uv run --locked python -m pytest tests/platform/tui tests/platform/ops -q`

Run: `uv run --locked python -m pytest tests/platform tests/test_risk.py tests/test_shadow_evidence.py -q`

Run: `uv run --locked python -m pytest -q`

Run Cargo fmt, Clippy with `-D warnings`, all locked tests, and release tests.

Run: `& scripts/verify-tui.ps1`

Expected: every required command exits zero; failures remain recorded and block
completion.

- [ ] **Step 4: Measure approved performance targets**

Record cached unlock-to-first-screen, event-to-visible latency, input latency,
idle CPU, continuous memory growth, 10,000-row filter/navigation, long chat
streaming, and clean process shutdown. Use at least 10 warmups and 100 measured
samples where applicable. Record median, p95, max, environment, build hash, and
raw samples. Do not subtract Python, broker, data, or model latency from their
own measurements; label each source.

Required gates: cached screen at or below 1 second, normal event visibility p95
at or below 250 ms, input p95 at or below 50 ms, idle TUI CPU p95 below 1 percent,
less than 10 MiB retained-memory growth during a one-hour synthetic stream, no
full-screen redraw for a one-panel event, responsive 10,000-row navigation, and
no orphan TUI or gateway process after stop. A miss is reported and blocks the
performance gate; thresholds are not changed after measurement.

- [ ] **Step 5: Run manual acceptance without financial side effects**

Verify password on every open, viewer Take Control, all ten screens, both themes,
three text sizes, keyboard/mouse parity, unavailable controls, generic Windows
notification, TUI close while fake daemon continues, safe shutdown preparation,
backup/restore against temporary state, and dirty-main auto-merge block. Do not
activate broker, Live, real training, real scheduler, or automatic merge.

- [ ] **Step 6: Reconcile every design acceptance criterion**

Write one row per criterion with `PASS`, `BLOCKED`, or `NOT ACTIVATED`, exact
test/receipt/file evidence, and reason. `BLOCKED` prevents completion;
`NOT ACTIVATED` is valid only for separately gated real-world capabilities whose
code path is disabled and tested.

- [ ] **Step 7: Commit**

Commit: `release(tui): verify V20 operations console`

## Phase acceptance

- Per-agent human chats stream and persist separately.
- Raw chats survive automatic context compression.
- V20 Core Memory stays within 2,000 words and all changes are reversible.
- Quiet Mode and continuous-work decisions are deterministic and resource-bound.
- No candidate training runs without an approved port.
- Notifications are generic and unlock remains required.
- DPAPI backup and staged restore pass corruption and traversal tests.
- Recovery blocks broker work until reconciliation and confirmation.
- Automatic maintenance rejects dirty main and all forbidden scopes.
- Final Python, Rust, broader, manual, and performance evidence is recorded.
- Real financial/scheduler/training/merge activation remains a separate authority event.
