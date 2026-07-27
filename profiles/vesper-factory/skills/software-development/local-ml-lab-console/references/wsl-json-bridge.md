# WSL JSON Bridge for Windows Tkinter Consoles

When a native Windows Tkinter app needs state from a WSL environment,
use a small read-only exporter script on the WSL side and invoke it via
`subprocess.run` from Windows. This avoids brittle UNC-path mounts and
console/TTY issues.

## Exporter script

Place in `scripts/wsl/export_state.py`:

```python
from __future__ import annotations

import json
from pathlib import Path


def _latest_file(directory: Path, pattern: str) -> Path | None:
    if not directory.is_dir():
        return None
    candidates = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _load_json(path: Path | None) -> object | None:
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


root = Path.home() / "vesper-model-storage"
state_root = root / "runs" / "state"

current = _load_json(state_root / "current.json")

events: list[object] = []
if (state_root / "events.jsonl").is_file():
    for line in (state_root / "events.jsonl").read_text(encoding="utf-8").splitlines()[-20:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

latest_report = _load_json(_latest_file(root / "runs" / "reports", "*.json"))
latest_evaluation = _load_json(_latest_file(root / "runs" / "evaluations", "*.json"))

print(json.dumps({
    "current": current,
    "events": events,
    "latest_report": latest_report,
    "latest_evaluation": latest_evaluation,
}, default=str))
```

## Windows caller

```python
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

WSL = Path(r"C:\Windows\System32\wsl.exe")
DISTRO = "Ubuntu-24.04"
EXPORTER = (
    "source /home/brennan/vesper-model-storage/venv/bin/activate && "
    "python /home/brennan/vesper-model-lab/scripts/wsl/export_state.py"
)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def load_snapshot() -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[str, Any] | None, dict[str, Any] | None, str]:
    result = subprocess.run(
        [str(WSL), "-d", DISTRO, "--", "bash", "-lc", EXPORTER],
        capture_output=True,
        check=False,
        text=True,
        creationflags=CREATE_NO_WINDOW,
        timeout=15,
    )
    if result.returncode != 0:
        return None, [], None, None, f"WSL read failed: {result.stderr.strip() or result.returncode}"
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, [], None, None, "WSL response was malformed"
    return (
        payload.get("current") if isinstance(payload.get("current"), dict) else None,
        [event for event in payload.get("events", []) if isinstance(event, dict)],
        payload.get("latest_report") if isinstance(payload.get("latest_report"), dict) else None,
        payload.get("latest_evaluation") if isinstance(payload.get("latest_evaluation"), dict) else None,
        "Refreshed",
    )
```

## Why not alternatives

| Approach | Problem |
|----------|---------|
| `\\wsl.localhost\Ubuntu-24.04\home\...` | Can disappear after sleep/resume or across Windows builds; path casing issues. |
| `wsl.exe some_script.sh` with TUI/curses | No TTY/TERM from a shortcut; curses crashes with `nocbreak() returned ERR`. |
| Running the whole app inside WSL with X forwarding | Requires an X server; not a smooth Windows desktop experience. |

## Testing the bridge

```bash
# From Windows (git-bash / MSYS)
wsl.exe -d Ubuntu-24.04 -- bash -lc 'source /home/brennan/vesper-model-storage/venv/bin/activate && python /home/brennan/vesper-model-lab/scripts/wsl/export_state.py'
```

You should get a single JSON object on stdout. If you see a Python
`ModuleNotFoundError`, the virtual environment was not activated.
