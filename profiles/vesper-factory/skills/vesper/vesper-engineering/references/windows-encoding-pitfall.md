# Windows File Encoding Pitfall

## Problem

On Windows, Python's `open()` defaults to `cp1252` (Windows-1252) encoding unless explicitly specified. This causes `UnicodeDecodeError` when reading files containing Unicode characters (em dashes, arrows, smart quotes, etc.).

## Error Signature

```
UnicodeDecodeError: 'charmap' codec can't decode byte 0x90 in position 995:
character maps to <undefined>
```

## Affected File Types

- YAML configs (`config/settings.yaml`)
- JSON files with Unicode content
- Markdown documentation
- Any text file with non-ASCII characters

## Fix

Always specify `encoding="utf-8"` when opening text files:

```python
# Wrong (breaks on Windows)
with open("config/settings.yaml") as f:
    config = yaml.safe_load(f)

# Correct (works everywhere)
with open("config/settings.yaml", encoding="utf-8") as f:
    config = yaml.safe_load(f)
```

## Where to Apply in VESPER

- `scripts/run_backtest.py` — loads `config/settings.yaml` and `config/universe.yaml`
- Any script that reads YAML/JSON/text files
- The dashboard launcher if it reads config files

## Historical Impact

2026-07-22: Backtest failed with `UnicodeDecodeError` at line 35 because `config/settings.yaml` contained Unicode characters and was opened without explicit encoding. Fix added `encoding="utf-8"` to both `open()` calls.
