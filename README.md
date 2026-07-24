# VESPER 2.0

Market-hours trading system for US equities with a live Tkinter dashboard.

## Setup

From Git Bash on Windows:

```bash
uv venv --python 3.11
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
cp .env.example .env
# Edit .env with your keys
```

## Tests

Use the project environment. The system `python` does not include every declared dependency.
Use a native Windows temporary path because the default pytest directory can be ACL-locked:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-pytest-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest -q --basetemp="$TMPROOT/pytest"
```

Remove the temporary directory after pytest exits. If Git Bash reports it is briefly busy,
wait for Python to exit and remove it from outside that directory.