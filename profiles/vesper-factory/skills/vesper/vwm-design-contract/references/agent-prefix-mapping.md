# Agent-Specific Issue Prefix Mapping

The Kanban board uses a generic `VQ-` prefix (Vesper Quality) for all
issue tracking across all agents. For operator readability, the VOT
Kanban panel relabels `VQ-` to an agent-specific prefix based on the
task's `assignee` field.

## Mapping

| Agent | Prefix | Full name |
|---|---|---|
| vesper-engineer | `VE-` | Vesper Engineer |
| vesper-clarke | `VC-` | Vesper Clarke |
| vesper-riley | `VR-` | Vesper Riley |
| vesper-morgan | `VM-` | Vesper Morgan |
| vesper-rez | `VZ-` | Vesper Rez |
| vesper-thomas | `VT-` | Vesper Thomas |
| vesper-steward | `VS-` | Vesper Steward |

## Implementation

```python
_AGENT_PREFIX = {
    "vesper-engineer": "VE-",
    "vesper-clarke": "VC-",
    "vesper-riley": "VR-",
    "vesper-morgan": "VM-",
    "vesper-rez": "VZ-",
    "vesper-thomas": "VT-",
    "vesper-steward": "VS-",
}

def _relabel(text: str, assignee: str) -> str:
    """Replace VQ- prefixes with agent-specific labels."""
    import re
    prefix = _AGENT_PREFIX.get(assignee, "VQ-")
    if prefix == "VQ-":
        return text
    return re.sub(r"\bVQ-", prefix, text)
```

## Important

- **Display-only** — the actual Kanban database retains `VQ-` prefixes.
  The relabeling happens at render time in the UI layer only.
- Applied to: task card titles, detail view title, body text, and
  summary text.
- If a task is unassigned or assigned to `default`, the generic `VQ-`
  prefix is kept (no relabeling).
