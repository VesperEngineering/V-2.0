# V20 Qwen Terminal Shortcut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one double-clickable Windows command script that opens a terminal running the approved local V20 model.

**Architecture:** A three-line `.cmd` launcher resolves the repository root from its own location, changes into that directory, and delegates the visible chat entirely to Ollama. It has no V20 controller integration, persistence, tools, scheduler, fallback, or wrapper output.

**Tech Stack:** Windows CMD, Ollama `qwen:64k`, Python standard-library test.

## Global Constraints

- Use exactly `qwen:64k`.
- Do not add fallback models or runtime behavior.
- Do not touch protected V20 data, credentials, broker/provider controls, or scheduler state.
- Preserve unrelated dirty files.

---

### Task 1: Add and verify the launcher contract

**Files:**
- Create: `tests/test_v20_qwen_terminal_launcher.py`
- Create: `V20 Qwen Chat.cmd`

**Interfaces:**
- Produces a double-clickable script whose exact lines are:

```text
@echo off
cd /d "%~dp0.."
ollama run qwen:64k
```

- The test reads the script as text and verifies the exact three-line behavior.

- [x] **Step 1: Write the failing test**

```python
from pathlib import Path
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "v20-qwen-chat.cmd"


class V20QwenTerminalLauncherTest(unittest.TestCase):
    def test_launcher_is_only_the_minimal_pinned_ollama_command(self):
        self.assertEqual(
            SCRIPT.read_text(encoding="utf-8").splitlines(),
            ["@echo off", 'cd /d "%~dp0.."', "ollama run qwen:64k"],
        )


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the test to verify it fails**

Run:

```powershell
python tests/test_v20_qwen_terminal_launcher.py
```

Expected: FAIL because `V20 Qwen Chat.cmd` does not exist.

- [x] **Step 3: Write the minimal launcher**

Create `V20 Qwen Chat.cmd` with exactly:

```bat
@echo off
cd /d "%~dp0.."
ollama run qwen:64k
```

- [x] **Step 4: Run the test to verify it passes**

Run:

```powershell
python tests/test_v20_qwen_terminal_launcher.py
```

Expected: PASS.

- [x] **Step 5: Run the live smoke check**

Run the equivalent non-interactive local command:

```powershell
ollama run qwen:64k "Reply only with V20_QWEN_READY"
```

Expected: Ollama responds using the installed `qwen:64k` model. If the local service is unavailable, report that exact native Ollama error without changing the launcher.

- [x] **Step 6: Inspect the final diff**

Run:

```powershell
git diff --check -- "V20 Qwen Chat.cmd" tests/test_v20_qwen_terminal_launcher.py
git status --short -- "V20 Qwen Chat.cmd" tests/test_v20_qwen_terminal_launcher.py
```

Expected: only the two intended new files are listed for this slice; unrelated existing dirty files remain untouched.
