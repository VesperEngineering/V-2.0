# Operator Activity Emit Pattern

`scripts/emit_worker_activity.py` is a convenience wrapper around `app.services.operator_activity.emit_activity()`. It fails with `ModuleNotFoundError: No module named 'app'` when called with the system Python because the repo root is not on `sys.path`.

## Correct invocation (venv + sys.path injection)

```bash
cd D:/vesper

.venv/Scripts/python.exe -c "
import sys; sys.path.insert(0, '.')
from app.services.operator_activity import emit_activity
emit_activity(worker='Riley', lane='governance', state='started', activity='short description here')
"
```

## Parameters

| Field | Required | Description |
|-------|----------|-------------|
| `worker` | Yes | Accountable worker name (e.g., `Steward`, `Morgan`, `Riley`, `Rez`, `Clarke`) |
| `lane` | Yes | Lane name from `.hermes/lanes.json` (e.g., `pipeline`, `telemetry`, `portfolio`, `governance`, `research`, `code_health`, `steward`) |
| `state` | Yes | One of: `cycle`, `blocked`, `ready`, `running`, `delegated`, `started`, `working`, `completed`, `skipped`, `failed`, `escalated` |
| `activity` | Yes | Short human-readable description (no credentials, prompts, or raw tool output) |

## When to emit

- **`started`** — just before dispatching a worker via `delegate_task`
- **`working`** — only when you have a concrete progress update from the worker
- **`completed`** — when the worker result returns successfully
- **`blocked`** or **`failed`** — when the worker returns with errors or the lane is blocked
- **`skipped`** — when the steward signals a delegation but you skip it per rotation policy
- **`cycle`** — on the steward marker, labeled `Steward` not `unassigned`

## Activity text rules

- Keep short (under 100 chars)
- Never include: credentials, prompts, chain-of-thought, raw tool output, hidden reasoning
- Format: `"action — detail"` (e.g., `"delegated portfolio"`, `"fixed VESPER_FACT_BASE.json: updated 6 issues"`)