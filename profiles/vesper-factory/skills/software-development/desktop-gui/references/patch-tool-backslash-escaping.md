# Patch tool backslash double-escaping

The `patch` tool (skill_manage action='patch') double-escapes backslashes
when the `new_string` argument contains literal `\n` sequences inside
f-strings or string literals. This bites when you break a long f-string
into multiple concatenated segments — a common ruff E501 fix pattern.

## Symptom

You call `patch` with `new_string` like:

```python
detail_text = (
    f"PRIMARY BLOCKER\n\n"
    f"{blocker.label}\n"
    f"State: {blocker.state}\n"
)
```

The file ends up with:

```python
detail_text = (
    f"PRIMARY BLOCKER\\n\\n"
    f"{blocker.label}\\n"
    f"State: {blocker.state}\\n"
)
```

Two backslashes + n, not one. The string now contains the literal text
`\n` (backslash-n) instead of a newline character.

## Detection

After every patch that touches string literals containing `\n`, verify
the actual bytes on disk with `cat -A` (or `od -c`) before moving on:

```bash
sed -n '327,336p' app/vot_tk.py | cat -A
# Healthy: f"PRIMARY BLOCKER\n\n"$
# Corrupt: f"PRIMARY BLOCKER\\n\\n"$
```

`cat -A` renders `\n` as `$` at line ends and renders literal backslash
as `\\`. A healthy f-string segment shows `BLOCKER\n\n"$` (one backslash,
the n, then the EOL marker). A corrupted one shows `BLOCKER\\n\\n"$`.

## Fix

Re-patch the corrupted lines with the same intended `new_string`. The
tool sometimes gets it right on the second attempt when the surrounding
context is different. If the second attempt also double-escapes, fall
back to one of:

- `write_file` to rewrite the whole file (safe for files under ~8K tokens)
- `sed -i 's/\\\\n/\\n/g'` to collapse the double-escapes in place
- Inline Python: `text = text.replace("\\\\n", "\\n")` then write

## When it fires

Observed when:
- `new_string` contains `f"...{var}\n..."` (f-string with `\n` literal)
- `new_string` contains `"...text\n"` (regular string with `\n` literal)
- The `old_string` being replaced also contained `\n` literals

Not observed with:
- Actual newlines in the source (the `\n` in the *file*, not in a string)
- Strings without backslash sequences

## Prevention

For ruff E501 fixes that require breaking long f-strings with `\n`
literals, prefer one of these instead of `patch`:

1. Extract a local variable to shorten the line (avoids breaking the
   f-string at all):
   ```python
   budget = pa.openrouter_remaining_budget_usd
   detail_text += f"  OR Budget:   ${budget:.2f}\n"
   ```

2. Use `write_file` to rewrite the whole file when many E501 fixes land
   in the same file — it's faster than chaining `patch` calls and avoids
   the escape bug entirely.

3. If you must use `patch` for a multi-line f-string break, verify the
   bytes with `cat -A` immediately after, and re-patch if doubled.

## Scope

This is a tool-level quirk, not a language or library issue. It affects
any Python file edited via `patch` where string literals contain
backslash escape sequences. The VOT Tkinter lint-cleanup session hit it
three times in `app/vot_tk.py` while breaking long `detail_text`
f-strings; each time `cat -A` caught it before the session moved on.
