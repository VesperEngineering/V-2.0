# Vesper Venv/PYTHONPATH Debugging Session

## Symptom
`python -m pytest tests/ --collect-only -q` showed 102 collection errors (later 95, then down to 2 after cleaning). All were `ModuleNotFoundError` or `ImportError` for C-extension modules: `numpy._core._multiarray_umath`, `torch_python.dll`, `pandas._libs.pandas_parser`, `pydantic_core._pydantic_core`.

## Root Cause
When you ran `python`, it resolved to **miniconda's Python 3.13** (`C:\Users\bgonn\miniconda3\python.exe`). However, `sys.path` loaded the **Hermes venv** site-packages (`...hermes-agent/venv/Lib/site-packages`) **before** miniconda's own site-packages (`...miniconda3/Lib/site-packages`). This was caused by `PYTHONPATH` including the Hermes venv path.

The Hermes venv was created with **Python 3.11** — all its C-extensions had `.cp311-win_amd64.pyd` suffixes. Python 3.13 cannot load 3.11-compiled C-extensions, producing the ModuleNotFoundError.

Packages affected (all 3.11-compiled in Hermes venv, blocking miniconda's native 3.13 copies):
- numpy 2.4.6 → 2.3.5 native
- torch 2.12.1 → 2.12.1 native (but crashes on 3.13 with internal assertion)
- pandas 3.0.3 → 3.0.4 native (3.0.4 had a segfault, pinned to 3.0.3)
- scikit-learn 1.9.0 → 1.9.0 native
- scipy 1.17.1 → 1.18.0 native (pinned to 1.17.1)
- pydantic_core 2.46.4 → 2.46.4 native

## Diagnosis Steps

### 1. Check Python version
```bash
which python      # → /c/Users/bgonn/miniconda3/python
python --version  # → Python 3.13.12
```

### 2. Check sys.path ordering
```python
python -c "import sys; [print(p) for p in sys.path if 'hermes' in p or 'miniconda' in p]"
# Shows Hermes venv BEFORE miniconda site-packages
```

### 3. Check where packages load from
```python
python -c "import numpy; print(numpy.__file__)"
# → ...hermes-agent/venv/Lib/site-packages/numpy/__init__.py  (WRONG)
```

### 4. Check individual error types
```bash
python -m pytest tests/test_tree_ranker_baseline_macro_feature_recheck.py --co -q 2>&1 | tail -15
# Shows the actual ImportError stack trace
```

## Fix Steps

### Phase 1 — Remove blocking 3.11 packages from Hermes venv
```bash
pip uninstall numpy torch pandas scikit-learn scipy -y
# pip runs from miniconda Python 3.13, removes from... wherever pip finds the package
# Verify with: python -c "import numpy; print(numpy.__file__)"
# Should now show miniconda3/Lib/site-packages/
```

### Phase 2 — Pin versions for compatibility
Some miniconda-native versions caused issues:
```bash
pip install "pandas==3.0.3" "scipy==1.17.1"
```
(This fixed a segfault in pandas 3.0.4's `maybe_promote` → `take_nd`)

### Phase 3 — Handle PyTorch 3.13 incompatibility
PyTorch 2.12.1 on Python 3.13 has an internal assertion:
```
storage_module && PyModule_Check(storage_module) INTERNAL ASSERT FAILED
```
Reinstall torch into the Hermes 3.11 venv:
```bash
"C:/Users/bgonn/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe" -m pip install torch
```
Then run tests with Hermes venv Python:
```bash
cd /d/vesper && "C:/Users/bgonn/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe" -m pytest tests/ -q --tb=line -rN
```

### Phase 4 — Clean up pydantic shadowing (same pattern)
```bash
pip uninstall pydantic pydantic_core pydantic-settings -y
# Miniconda has native cp313 copies already installed
```

## Results Before → After

| Metric | Before | After |
|--------|--------|-------|
| Collection errors | 102 | 0 |
| Tests collected | 2,798 | 3,569 |
| Tests passed | N/A (couldn't run) | 3,470 |
| Tests failed | N/A | 37 (pre-existing) |
| Tests skipped | N/A | 64 |

## Key Verification Commands
```bash
# Collection check
python -m pytest tests/ --collect-only -q | tail -3

# Full run
python -m pytest tests/ -q --tb=line -rN | tail -5

# Check specific package source
python -c "import numpy; print(numpy.__file__)"
```

## Notes
- The `vesper-qlib311` conda env (`C:\Users\bgonn\miniconda3\envs\vesper-qlib311\`) also works and uses Python 3.11 natively with matching packages.
- The Hermes venv's own Python (`...hermes-agent/venv/Scripts/python.exe`) is Python 3.11.15 — this is the safest environment for Vesper work.
- A `~/.bashrc` addition (`export PATH="C:/Users/bgonn/AppData/Local/hermes/hermes-agent/venv/Scripts:$PATH"`) can make the Hermes venv Python the default for future terminals.