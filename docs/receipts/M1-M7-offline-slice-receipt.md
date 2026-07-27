# M1-M7 Offline Native Platform Slice Receipt

- Recorded: 2026-07-27
- Baseline branch: `main`
- Baseline commit: `9f9df7cf483bd77603dd5bf8c145c80c58aeb0e2`
- Environment: Python `3.11.15`, uv `0.11.32`, Windows
- Final result: first local LangGraph vertical slice complete and verified

## Milestone reconciliation

| Milestone | Result | Delivered |
| --- | --- | --- |
| M1 dependency compatibility | Complete for this slice | LangGraph `1.2.9`, SQLite checkpoint/Store `3.1.0`, and reviewed transitive closure locked. LangSmith `0.10.10` is accepted only as inert transitive code; LangMem is deferred. |
| M2 typed contracts | Complete | Strict versioned Pydantic contracts, UTC/revision provenance, fail-closed decisions, nested evidence authority, correction budget, and authoritative acceptance gates. |
| M3 persistence/evidence | Complete | Local `SqliteSaver`, `SqliteStore`, authorized Store adapter, atomic SHA-256 filesystem evidence, manifests, recovery metadata, close/reopen and corruption tests. |
| M4 Codex boundary | Complete offline | Lazy SDK adapter with start/resume, sandbox/permission policy, event/result receipts, timeout/cancellation/usage-limit classification. The real local test remains opt-in and was not enabled. |
| M5 profiles/local memory | Complete for this slice | Three native profiles, hashed immutable policy records, Store-backed isolated namespaces, validated-only candidates, append-only contradiction lineage, and fake consolidation emitter. No LangMem package. |
| M6 native graph | Complete | Product → Development → deterministic validation → Risk Review, shared three-failure correction budget, real interrupt, persisted explicit decision, terminal acceptance/rejection, and process-reopen recovery. |
| M7 CLI lifecycle | Complete for persisted local runs | Status, receipts, evidence, pending approvals, approve, reject, resume, and cancel use the local graph/checkpoint/Store service. Help is side-effect free. `create` requires an injected approved specialist composition and otherwise fails closed. |

## Architecture delivered

The new `vesper.platform` package is isolated from trading, broker, provider, Massive, scheduler,
credential, model-promotion, and Tk code. LangGraph owns deterministic routing and interrupts;
SQLite owns checkpoints and local Store records; the filesystem evidence store owns immutable
artifact bytes and hashes. Generated specialist output is never acceptance. Acceptance requires a
matching deterministic validation pass, independent Risk approval, a controller-validated decision
persisted in Store, and an explicit graph resume.

The approval node independently reloads and compares the persisted decision, so direct compiled-
graph invocation cannot bypass the controller. Receipt, validation, and risk evidence must match the
current run, task, and repository revision. Accepted, rejected, and cancelled views never expose a
stale pending approval.

LangSmith is not imported or used as an application service. `runtime_env.py` force-disables current
and legacy tracing flags before LangGraph imports. The fresh-process deny-egress proof starts with
tracing enabled, verifies the policy overrides it, and records zero socket attempts during Store,
checkpoint, interrupt, persisted approval, and resume operations.

## Platform files created

```text
docs/receipts/M1-dependency-receipt.md
docs/receipts/M1-M7-offline-slice-receipt.md
docs/superpowers/plans/2026-07-27-native-agent-platform-offline-vertical-slice.md
profiles/native/v20-development/SOUL.md
profiles/native/v20-development/profile.yaml
profiles/native/v20-product/SOUL.md
profiles/native/v20-product/profile.yaml
profiles/native/v20-risk-review/SOUL.md
profiles/native/v20-risk-review/profile.yaml
tests/platform/offline_graph_probe.py
tests/platform/test_authority_boundaries.py
tests/platform/test_cli.py
tests/platform/test_cli_help_isolation.py
tests/platform/test_codex_adapter.py
tests/platform/test_codex_local_integration.py
tests/platform/test_contracts.py
tests/platform/test_dependencies.py
tests/platform/test_evidence.py
tests/platform/test_langsmith_network_isolation.py
tests/platform/test_memory.py
tests/platform/test_persistence.py
tests/platform/test_profiles.py
tests/platform/test_runtime_environment.py
tests/platform/test_service.py
tests/platform/test_workflow.py
vesper/platform/__init__.py
vesper/platform/cli.py
vesper/platform/codex.py
vesper/platform/contracts.py
vesper/platform/evidence.py
vesper/platform/memory.py
vesper/platform/persistence.py
vesper/platform/profiles.py
vesper/platform/runtime_env.py
vesper/platform/service.py
vesper/platform/workflow.py
```

## Existing platform-foundation files modified

```text
README.md       # current native CLI and verification boundaries
pyproject.toml  # direct compatible LangGraph/SQLite pins and existing platform dependencies
uv.lock         # reviewed 79-package resolution
```

No trading, portfolio, risk-limit, schedule, provider, Massive, model, or historical-evidence
implementation was changed by the LangGraph continuation. Other dirty working-tree paths are the
accepted M0/maintenance baseline and were preserved.

## Test-first failures and repairs

- SQLite Store tests failed with `cannot start a transaction within a transaction`. Source review
  showed the official factory uses autocommit; the dedicated Store connection now uses
  `isolation_level=None`.
- An adversarial test proved a caller could resume the compiled graph directly with a fabricated
  approval. The human-approval node now requires an identical Store-persisted decision.
- Review found foreign nested evidence could retain valid outer authority. Typed contracts and graph
  checks now recursively bind evidence to run/task/revision, with specialist/validation/risk tests.
- Terminal views retained the historical approval request as pending. Pending state is now gated on
  both `awaiting-approval` and the live interrupt.
- The initial network proof began with tracing disabled. It now begins with tracing enabled, verifies
  V20 forces every supported flag off before LangGraph imports, and retains the socket canary/guard.
- The LangGraph resolution requires `websockets==15.0.1`; the prior lock had `16.1.1`. Resolution and
  `uv pip check` confirm compatibility with LangGraph SDK and existing packages.

## Exact material commands executed

```powershell
uv lock
uv tree --locked --package langgraph --depth 4
uv tree --locked --invert --package langsmith
uv tree --locked --invert --package langchain-core
$env:UV_PROJECT_ENVIRONMENT="$env:LOCALAPPDATA\Temp\v20-langgraph-20260727"
uv sync --locked --all-groups
python -m pytest tests/platform/test_dependencies.py tests/platform/test_runtime_environment.py -q
python -m pytest tests/platform/test_persistence.py -q
python -m pytest tests/platform/test_workflow.py -q
python -m pytest tests/platform/test_service.py tests/platform/test_cli.py -q
python -m pytest tests/platform/test_langsmith_network_isolation.py -q
ruff format vesper/platform tests/platform
ruff check vesper/platform tests/platform
python -m pytest tests/platform -q
python -m pytest tests -q
```

Fresh locked final verification:

```powershell
$env:UV_PROJECT_ENVIRONMENT="$env:LOCALAPPDATA\Temp\v20-langgraph-final-20260727"
uv sync --locked --all-groups
python -m pytest tests -q --basetemp "$env:LOCALAPPDATA\Temp\v20-langgraph-final-suite"
python -m pytest tests/platform -q --basetemp "$env:LOCALAPPDATA\Temp\v20-langgraph-final-platform"
python -m pytest tests/test_imports.py -q --basetemp "$env:LOCALAPPDATA\Temp\v20-langgraph-final-imports"
$env:PYTHONPYCACHEPREFIX="$env:LOCALAPPDATA\Temp\v20-langgraph-final-compile\pycache"
python -m compileall -q vesper scripts tests
ruff check vesper scripts tests
ruff format --check <33 changed Python files>
uv lock --check
uv pip check --python "$env:LOCALAPPDATA\Temp\v20-langgraph-final-20260727\Scripts\python.exe"
vesper-agent --help
git diff --check
```

## Exact final results

- Fresh locked sync: 79 packages resolved; 78 installed plus editable V20; success.
- Complete scoped V20 suite: `431 passed, 1 skipped in 48.10s`.
- Focused platform suite: `107 passed, 1 skipped in 6.23s`.
- The one skip is the explicitly gated real local Codex SDK test; it was not enabled.
- Isolated import verification: `56 passed in 20.86s`.
- First-party compilation with external bytecode cache: success, no output.
- Ruff lint: `All checks passed!`.
- Changed-file format check: `33 files already formatted`.
- `uv lock --check`: 79 packages resolved; success.
- Fresh-environment `uv pip check`: 78 packages checked; all compatible.
- `vesper-agent --help`: exit 0; no persistence directory was created.
- `git diff --check`: exit 0; only pre-existing Windows LF/CRLF warnings.
- Direct LangSmith-import scan: no matches.
- Deferred-provider lock scan (`langmem`, full `langchain`, OpenAI/Anthropic LangChain providers): no matches.

## Remaining blockers and residual risks

1. The installed CLI cannot execute `create` without an approved specialist composition. This is
   deliberate: shipping deterministic test fakes as production agents would manufacture evidence,
   while invoking real Codex was outside this slice. Existing graph-backed persisted-run lifecycle
   commands work and are integration-tested.
2. LangMem remains deferred pending compatibility, provider-closure, billing, and authority review.
   The Store-backed typed memory boundary preserves that option without depending on it.
3. Real Codex authentication/execution was not attempted. The opt-in boundary test is the next
   operator-controlled check and cannot by itself prove every OS sandbox guarantee.
4. The deny-egress test proves the fixed Python execution path makes no socket attempt; it is not an
   OS-level network namespace and cannot constrain arbitrary future user node code.
5. SQLite is intentionally an initial single-host persistence choice. Multi-process contention,
   schema migration policy, backup/restore, and operational retention need separate review before
   production use.

## Recommended next smallest expansion

Define one operator-approved local specialist composition behind the existing ports, with a
deterministic validator command allowlist and repository/worktree permission policy. First run it
through the opt-in Codex boundary in a disposable worktree with network denied; do not connect it to
trading, schedules, providers, or automatic acceptance.
