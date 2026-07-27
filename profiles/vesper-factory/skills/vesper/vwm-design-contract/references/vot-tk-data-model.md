# VOT Tkinter Data Model Mapping

Maps VOT's `TerminalSnapshot` fields to Tkinter UI components.

## Snapshot source

```python
from app.services.operator_terminal_status import load_dashboard_snapshot
# Requires 4 tracker args (keyword-only):
from app.services.operator_codex_activity import CodexActivityTracker
from app.services.operator_workspace_activity import (
    WorkspaceEventTracker, WindowsDirectoryEventSource, GitActivityTracker,
)
from app.services.operator_provider_telemetry import build_provider_telemetry_supervisor

snap = load_dashboard_snapshot(
    root,
    codex_tracker=CodexActivityTracker(root),
    workspace_tracker=WorkspaceEventTracker(root, started_at=observed),
    git_tracker=GitActivityTracker(root),
    event_source=WindowsDirectoryEventSource(root),
    provider_telemetry=provider_supervisor.snapshot(),
)
```

**Import gotcha:** `WorkspaceEventTracker`, `WindowsDirectoryEventSource`, AND
`GitActivityTracker` all live in `operator_workspace_activity` — NOT in
separate modules. Do not import from `operator_workspace_events` or
`operator_git_activity` (they don't exist).

## TerminalSnapshot fields → UI components

| Snapshot field | Type | UI component |
|---|---|---|
| `observed_at` | `str` | Appbar sync time, metrics freshness |
| `session` | `str` | Appbar `[PAPER {session}]` bracket |
| `authority_state` | `str` | Appbar `[AUTHORITY {state}]` bracket |
| `overall_state` | `str` | Appbar `[EVIDENCE {state}]` bracket |
| `pipeline` | `tuple[StatusRow, ...]` | Rail: evidence spine cards + queue counts |
| `first_incomplete` | `StatusRow \| None` | Focus: primary blocker title + metrics |
| `issues` | `tuple[IssueRow, ...]` | Detail tab: ISSUES section |
| `approvals` | `tuple[ApprovalRequest, ...]` | Detail tab: APPROVALS section |
| `cadence` | `tuple[StatusRow, ...]` | Detail tab: CADENCE section |
| `receipts` | `tuple[ReceiptRow, ...]` | RECEIPT tab |
| `provider_accounting` | `ProviderAccountingSnapshot \| None` | Detail tab: PROVIDER CAPACITY + appbar usage |
| `autonomous` | `AutonomousSnapshot \| None` | Detail tab: RECENT ACTIVITY |
| `connection_state` | `str` | (available, not yet rendered) |
| `errors` | `tuple[str, ...]` | (available, not yet rendered) |
| `authority_failures` | `tuple[str, ...]` | (available, not yet rendered) |
| `next_safe_task` | `str` | (available, not yet rendered) |

## StatusRow (most common data structure)

```python
@dataclass
class StatusRow:
    key: str           # e.g. "freshness"
    label: str         # e.g. "Freshness"
    state: str         # "pass" | "fail" | "stale" | "missing_source" | "running" | "waiting"
    detail: str        # human-readable detail, e.g. "2026-07-13"
    source_path: str   # path to evidence file, e.g. "PROJECT_ADVANCEMENT.md"
    timestamp: str     # last update time
```

State values for status dot coloring:
- `running` / `active` → warm-white filled dot
- `fail` / `failed` / `blocked` / `missing` / `missing_source` → red filled dot
- `pass` / `passed` / `ready` / `complete` → green filled dot
- `stale` → amber filled dot
- `waiting` / `not_due` / `not_configured` → hollow muted dot

## ProviderAccountingSnapshot

```python
@dataclass
class ProviderAccountingSnapshot:
    openai_usage: str
    openrouter_usage: str
    openrouter_remaining_budget_usd: float | None
    openai_remaining_percent: float | None
    reconciliation: str
    # ... more fields for tokens/requests
```

Appbar usage summary: `"OAI {percent}%  ·  OR ${budget}"`

## Tab content builders

- **DETAIL**: primary blocker + evidence spine + provider capacity + issues + approvals + cadence + recent activity
- **SOURCE**: source_path for each pipeline stage (label, state, source, receipt, updated)
- **RECEIPT**: all evidence receipts (receipt_id, family, date, path, status, errors)

## Polling

- `POLL_SECONDS = 5` (VOT) vs `2` (VWM)
- Background thread fetches snapshot → `queue.Queue` → main thread drains via `root.after(150, self._drain_queue)`
- `_first_loaded` flag prevents "CONNECTING…" from showing after first successful sync
