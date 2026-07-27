# Vesper-style terminal activity feeds

Use this pattern for a Prompt Toolkit operator dashboard that monitors autonomous workers.

## Data contract

Do not infer worker activity from a coordinator cycle log. Use an append-only structured JSONL stream with bounded fields:

```json
{
  "ts": "2026-07-15T02:24:59.279840+00:00",
  "worker": "Morgan",
  "lane": "portfolio",
  "state": "started",
  "activity": "reviewing portfolio construction"
}
```

Recommended states: `delegated`, `started`, `working`, `completed`, `blocked`, `failed`.
Emit coordinator events separately (`worker: Steward`). A delegation event is not proof that the worker started or completed work.

Write through a fail-closed emitter that:
- bounds free-form text;
- redacts credential-like fields (`password`, `secret`, `token`, `credential`, `api_key`);
- never lets logging failure crash the worker or TUI;
- appends atomically enough for one-line JSONL events.

Keep a legacy-log fallback during migration, but mark it as inferred/coordinator activity rather than worker activity.

## Rendering contract

Render the live feed as a fixed-width table, not free-form sentences:

```text
 TIME   ACTIVITY                   WORKER
 2m14s  delegated portfolio        Morgan
 1m03s  cycle 25                   Steward
   41s  code health                Clarke
```

- right-align elapsed time;
- reserve a fixed activity width and truncate with ellipsis rather than wrapping;
- reserve a fixed worker width, left-aligned at the same x-position;
- keep newest bounded rows visible and never allow one row to become two lines;
- wrap narrative learnings separately using the actual column width, with indented continuation lines.

Use semantic colors on a muted slate base: pass green, blocked/failed red, waiting/stale amber, running blue, delegated purple, and restrained worker-specific accents. Prompt Toolkit class fragments must use valid class syntax (`class:dashboard class:activity-meta`), not `class:dashboard activity-meta` (the latter is parsed as a color and raises `ValueError: Wrong color format`).

Add deliberate blank rows or separators between summary, lanes, live activity, and learnings. Verify at both 3-column and 2-column widths; assert rendered lines stay within the viewport.

## Runtime diagnostics

Catch source-boundary refresh errors and retain the last good snapshot. Record a redacted traceback to a project-local error log such as `.hermes/operator_terminal_error.log`. The on-screen error should remain sanitized (`Refresh failed: RuntimeError`), while the file log contains diagnostic detail with secrets removed.

When a Windows Terminal child exits with only `FAILED: ValueError`, reproduce using the exact project `.venv` interpreter and test Prompt Toolkit application construction with `DummyOutput` before changing launch mechanics. Verify the actual `.lnk`/launcher separately after source-level tests pass.

## Verification

Use a repository-local pytest base directory on Windows if the default pytest temp root has access-control problems:

```bash
python -m pytest tests/test_operator_terminal_layout.py \
  tests/test_operator_terminal_controller.py \
  tests/test_operator_terminal_hardening.py -q --tb=short \
  --basetemp='D:/vesper/.tmp/pytest-tui'
```

Also run:
- Python compilation for the changed renderer/status/emitter modules;
- a deterministic render at 180 columns and a narrower 2-column width;
- a forced refresh exception probe proving last-good-state retention, redacted log output, and no TUI crash;
- the exact Windows launcher and HWND geometry check for desktop delivery.
