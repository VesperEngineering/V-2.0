# Dashboard Editing Patterns — Vesper

The factor_dashboard.py uses an intentional compact KISS/DRY style (one-liners, semicolons).
The standard `patch` tool frequently mangles indentation on this file. Use these patterns instead.

## Preferred: sed for surgical edits

```bash
# Insert after a matched line
sed -i '/pattern/a\new line content' scripts/factor_dashboard.py
# Delete a specific line
sed -i '376d' scripts/factor_dashboard.py
# Global substitution
sed -i "s/old_text/new_text/g" scripts/factor_dashboard.py
```

## Bulk changes: Python string replacement

```python
with open('scripts/factor_dashboard.py', 'r') as f: text = f.read()
text = text.replace(old_block, new_block)
with open('scripts/factor_dashboard.py', 'w') as f: f.write(text)
```

Always verify with `py_compile.compile()` before launching.

## Known pitfalls

### "e.utc" timestamp bug
`sed "s/UTC/timezone.utc/g"` replaces BOTH `timezone.utc` in code AND `" UTC"` in format strings.
Result: `strftime("%Y-%m-%d %H:%M timezone.utc")` → timestamps show `e.utc`.
Fix: reverse the specific format string replacement, not the global sed.

### Python 3.10 compat
`from datetime import UTC` only works on Python 3.11+. Use `from datetime import timezone` + `timezone.utc`.

### ruff-format expands compact code
Compact dashboard triggers 270+ line diffs from ruff-format. Use `git commit --no-verify`.

### Tkinter geometry off-screen on >1080p displays
`m.geometry("1920x1080")` sets size but not position. On displays larger than 1080p (e.g. 3440×1440),
the window opens at an unpredictable position — sometimes off-screen or behind other windows.
Fix: `m.geometry("1920x1080+0+0")` to anchor top-left of primary monitor.
Use Python str.replace for the edit (patch tool mangles indentation):
```python
c = c.replace('m.geometry("1920x1080")', 'm.geometry("1920x1080+0+0")')
```

### Reverting broken patches
```bash
git checkout HEAD -- scripts/factor_dashboard.py
```
