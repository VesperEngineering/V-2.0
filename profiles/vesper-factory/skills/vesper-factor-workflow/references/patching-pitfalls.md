# Patching Patterns — When the Patch Tool Fails

The `patch` tool frequently fails on certain files with:
- **Escape-drift**: `Escape-drift detected: old_string and new_string contain the literal sequence '\\\\"'`
- **Multiple matches**: `Found 4 matches for old_string. Provide more context.`

These failures concentrate on:
- `aggregator.py` (dense JSON/dict constructs with nested quotes)
- Any file with escaped characters in patch strings
- HTML files with inline SVG (mangles indentation)

## Workaround: Python `str.replace()` via write_file

When patch fails on a `.py` file:

```python
# Write a patch script to /d/vesper/agg_patch.py
text = open(r"C:\Users\bgonn\vesper-dashboard\aggregator.py").read()
# Use exact text from the file (copy-paste from read_file output)
text = text.replace("old exact text", "new exact text")
open(r"C:\Users\bgonn\vesper-dashboard\aggregator.py", "w").write(text)
```

Then run and delete the patch script:
```bash
cd /d/vesper && $PY agg_patch.py && rm agg_patch.py
```

## When to use this pattern

- The patch tool fails twice on the same file
- You're inserting multi-line blocks with mixed quoting
- You're working on `aggregator.py` or `data-binder.js`

## When to keep trying patch

- Simple find-and-replace with unique context
- The error is "not unique" — add more surrounding lines
- The error is "not found" — the file format changed, re-read it

## Cleanup

Always delete temporary patch scripts after they succeed. They pollute the repo
and create unnecessary commits. Pattern: `&& rm agg_patch.py` in the same terminal call.
