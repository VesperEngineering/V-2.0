# V20 Ratatui Console Verification

Status: **PACKAGE BUILT; FOUNDATION AND COMPONENT GATES VERIFIED; FULL PRODUCTION RELEASE BLOCKED**

This receipt separates tested console behavior from capabilities that are not
connected or authorized. `NOT ACTIVATED` means the control or production source
is intentionally off. `UNVERIFIED` means no direct real-terminal or manual test
was run. `BLOCKED` is a known release blocker.

## Delivered

- Ratatui client with the fixed ten-screen shell, warm-white/charcoal themes,
  Compact/Standard/Large Text, keyboard and mouse mappings, details, search,
  notes, separate agent chats, alerts, control menus, and durable receipts.
- Current-user Windows named-pipe gateway with password lock, explicit Take
  Control lease, strict versioned contracts, bounded frames, and fail-closed
  reconnect behavior.
- Controller projections, event/search stores, managed-memory read view,
  operations policies, generic notification support, encrypted backup/cache,
  recovery, and local-maintenance safety contracts.
- Exact package: `dist/tui/vesper-ratatui-console.exe`, `README.md`, and
  `build-receipt.json`. No shortcut was installed and V20 was not started.

## Design acceptance reconciliation

| Criterion | Status | Evidence and limit |
| --- | --- | --- |
| Ten-screen shell and strict core contracts | PASS | Rust screen, contract, snapshot, state, and input suites. Missing production sources render `UNAVAILABLE`; fixtures never enter the running gateway. |
| Accepted deep screen-detail contracts | PASS | Direct strict fields now carry agent plan/tool/file/context, final model regime/gates, blocked-risk/circuit-breaker detail, source dependencies/raw logs, and System recovery/Qwen detail. Deep-screen Rust suites pass. |
| Impact layout A and Jira-style Agents board | PASS | `tests/screens_market.rs`, `tests/screens_agents.rs`, snapshots, fixed-column board tests. |
| State-changing actions are controller-validated and receipt-backed | PASS | Python command registry/gateway suites and Rust command/control suites. Only currently reviewed note, alert-dismiss, layout-reset, approval, and bounded-enqueue adapters can become conditional. |
| Rust does not write authoritative V20 state | PASS | All mutations cross the Python gateway; projection ports are read-only. Broker, model, risk, runtime, scheduler, backup, and source-control effects remain disabled. |
| Password and Take Control ownership | PASS | Automated first-run, unlock, viewer/controller, reconnect, lock, and multi-session presence tests pass. Real interactive password entry was not manually exercised. |
| Stale or unavailable state disables unsafe actions | PASS | Strict freshness, control-pair, sequence-gap, cache, confirmation, and unavailable-capability tests pass. |
| Portfolio movement waits for execution and broker read-back | PASS | Contract/fake tests preserve current/proposed/approved columns and executed-only rank. Production portfolio/order/broker reads are `NOT ACTIVATED` because no approved controller adapter is configured. |
| Agent chat, Qwen context, memory, training, and approval limits | PASS | Policy/component tests cover separate bounded chats, one 64K Qwen lease, compression, 2,000-word managed memory, reversible archive, activation grants, and approvals. Continuous work, curation, training, deletion, and merge remain `NOT ACTIVATED`. |
| Runtime lifecycle and high-risk operations | NOT ACTIVATED | Runtime, service, scheduler, training, deletion, merge, broker, risk, and Live adapters or activation grants remain off. |
| Production backup/restore command path | BLOCKED | P2 scope gap: DPAPI backup/restore passes temporary-state tests, but the production gateway does not inject a `BackupCommandPort`; the TUI buttons remain disabled. |
| Notification implementation | PASS | Generic-content, activation-ID, cleanup, failure-health, and locked-console tests pass. Actual Windows display/activation/Action Center cleanup remains `UNVERIFIED`. |
| Required focused tests | PASS | `session-verification.json` records Ruff, 1,313 focused Python passes, 1,313 reproducible-script passes, Rust debug/release, and README/script checks. |
| Broader repository suite | BLOCKED | Environment blocker: 2,070 passed, 5 skipped, and 4 existing OpenCode process-tree tests failed because this sandbox denied their required Windows `taskkill`; no failure was attributed to the TUI slice. |
| Component performance evidence | PASS | Component renderer, real DPAPI/disposable gateway, and 10-minute Tick/render CPU gates pass with raw samples in `performance.json`. |
| One-hour retained-memory component gate | PASS | Release test ran for `3,608.02 s`; peak live-allocation growth was `9,068,088` bytes and end growth was `5,936` bytes, both below `10,485,760`. PrivateUsage is informational. |
| Full-process performance acceptance | UNVERIFIED | Real ConPTY, production named-pipe, native/Python/GPU memory, and complete-process startup, idle, and shutdown remain unverified. |
| Protected data and credentials remain untouched | PASS | No changed path is under `vesper/data/massive/` or `vesper/data/model_research/`; no credential was used, printed, stored, or tested. |
| High-risk activation remains separate | PASS | Broker, orders, Live, risk changes, runtime/service control, scheduler, training, candidate deletion, automatic merge, and push remain disabled or unavailable. |

## Production gaps

| Area | Status | Reason |
| --- | --- | --- |
| Portfolio, orders, market data, models, regime, rebalance timing, and Qwen usage mirror | NOT ACTIVATED | V20 has no reviewed controller-owned production adapters for these views. Broker/account reads also require separate approval. Screens fail closed. |
| Deeper agent plan/tool/file/context detail | PASS | Direct strict fields and the detail renderer carry the approved fields; focused deep-screen tests pass. |
| Model, risk, data, memory-use, and System deep detail | PASS | Direct strict fields and screen renderers carry the approved final-regime/gate, blocked-action/circuit-breaker, source-dependency/raw-log, agent-memory-use, recovery, backup-health, and Qwen-system fields. |
| Real Windows terminal input and event-to-visible latency | UNVERIFIED | Component/TestBackend measurements are not ConPTY or Crossterm end to end. |
| Full Windows process startup, unlock, idle CPU, shutdown, and memory | UNVERIFIED | The one-hour Rust component gate passed, but it does not include all native, Python, GPU, VRAM, named-pipe, or terminal costs. |
| Permanently hung admitted gateway handler | PASS | `_GatewayCoordinator.stop()` now uses a bounded join; late disconnect returns without waiting when the handler remains hung. Regression and full gateway tests pass. The handler remains a daemon thread and is not force-cancelled. |
| Production backup/restore invocation | BLOCKED | The service and temporary-state tests exist, but no production backup command adapter is connected. |
| Manual Windows console acceptance | UNVERIFIED | All ten screens, password, themes, three text sizes, keyboard/mouse parity, close behavior, unavailable controls, toast, temporary backup/restore, dirty-main block, and shortcut launch were not manually completed. No user password was requested or stored; no shortcut was installed. |

## Fresh verification

- Changed Python files: Ruff format/check pass, 48 files.
- Focused Python: `1,313 passed` in `160.696 s`.
- Reproducible script: `1,313 passed` in `160.696 s`; Rust format, Clippy, and all-target tests pass.
- Full Python repository: `2,070 passed, 5 skipped, 4 sandbox-taskkill failures` in `311.35 s`.
- Rust debug: `428 passed, 4 ignored`; release: `428 passed, 4 ignored`.
- README and packaging-script checks: `15 passed` in `7.00 s`.
- Idle Tick/render component: p95 `44` percent-basis-points (`0.44%`), max
  `59` (`0.59%`), gate `< 1%`.
- Cached DPAPI/disposable-gateway first frame: p95 `316,026,400 ns`, max
  `334,389,200 ns`, gate `<= 1 s`.
- One-hour Rust retained memory: peak growth `9,068,088` bytes; end growth
  `5,936` bytes; gate `< 10,485,760` bytes.
- Full command receipt: `TUI testing/results/verification-commands.json`.
- Session console receipt: `TUI testing/results/session-verification.json`.
- Performance raw samples: `TUI testing/results/performance.json`.
- Fresh shutdown regression: `tests/platform/tui/test_gateway.py` passed; full
  gateway suite `57 passed`; full TUI/operations Python suite `1,314 passed`.
- Package executable: `5,321,216` bytes, SHA-256
  `c0c253c85897a619a7b03c9068e411fefa7685d1854e5c2918bde482e8ca831c`.
- Packaged README SHA-256:
  `00e6436d9caa6efcdbd2425ba3ce16f5102724fd6f639386131bdfe041bc77cd`.
- Build receipt SHA-256:
  `87a33eb079bf2edc5b9196519ca4daa09f7cd9974acdca0bc50b9052ea68ec43`.

## Delivery state

- Branch: `codex/vesper/ratatui-console`.
- HEAD: `8174e0531d2c9e7334314a796097614caa0cd079` plus a verified uncommitted final slice.
- Source manifest: 130 changed/untracked source files, SHA-256
  `89625e960f7648f06ced178b6728a493304288f5cea279f0f9be1d1eb2d797a3`.
- Final commit is blocked because the sandbox denied creation of the linked-
  worktree `index.lock`. No stale lock file is present. Existing commits are
  intact. No merge or push was attempted.
- Pre-existing untracked `=` and sandbox-created `.pytest-*` directories were
  preserved and were not packaged.
