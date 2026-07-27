# Development Workflow Gotchas

Recurring tool quirks and workarounds encountered during Vesper development.

## Patch Tool Escape-Drift

When `patch` fails with "Escape-drift detected" or "old_string and new_string are identical":

1. The file was read via `read_file` with `limit` pagination — the patch tool has a partial view of the file.
2. Fix: read the whole file without pagination (pass `limit=0` or read the full `total_lines`), or use the Python heredoc workaround:

```python
# In a terminal block:
python - <<'PY'
p = 'path/to/file.py'
content = open(p).read()
content = content.replace(old_string, new_string)
open(p, 'w').write(content)
import py_compile
py_compile.compile(p, doraise=True)
print('OK')
PY
```

This bypasses the escape handling entirely. The `patch` tool also has fragile indentation handling with `prompt_toolkit`-formatted output — when indentation gets corrupted, the Python workaround is more reliable.

## Version Tracking

Add version metadata to any file that receives iterative edits:

```python
"""Module docstring.

Version History:
  1.0.0  Initial version.
  1.0.1  Added feature X.
"""

__version__ = "1.0.1"
```

Bump the version and note what changed on each edit. This prevents the "old_string and new_string are identical" problem when the patch tool's snapshot is stale and helps trace regressions across sessions.

## PROMPT_TOOLKIT_OUTPUT=ansi

When a Windows Python runs in a non-Windows console (git-bash, mintty, cygwin, WSL without Windows interop), `prompt_toolkit` fails with `NoConsoleScreenBufferError`. Fix by forcing ANSI output mode before any dashboard code:

```python
import os
os.environ["PROMPT_TOOLKIT_OUTPUT"] = "ansi"
```

For console window size on Windows, add to `main()`:

```python
try:
    import subprocess
    subprocess.run(
        ["cmd.exe", "/c", "mode con: cols=256 lines=33"],
        capture_output=True, timeout=5,
    )
except Exception:
    pass
```

## Module Not Found When Running Directly

If you get `ModuleNotFoundError: No module named 'app'`, you ran the file directly (`python path/to/file.py`) instead of as a module (`python -m app.module_name`). The `-m` flag adds the current directory to `sys.path`. Check the shortcut target — it should use `-m`, not a file path.