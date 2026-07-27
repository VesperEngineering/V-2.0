# Factor Governance Audit Checklist

When a new factor is added (or a batch of factors is implemented), run this
8-point governance audit to catch design defects, registration drift, and
documentation gaps before the next pipeline run.

## Audit Points

### 1. Pattern — Concrete Subclass, Not Factory

Each factor must be a concrete class extending `BaseFactor`, with its own
`name` and `required_data` class attributes.  Composite/interaction factors
should instantiate parent factors directly in `_compute()` and call their
`_compute()` method — not a generic factory.

```python
# Correct
class MyFactor(BaseFactor):
    name = "my_factor"
    required_data: list[str] = []

    def _compute(self, *, root=".", date_stamp=None, universe=None, **kwargs):
        parent = ParentFactor()
        result = parent._compute(root=root, date_stamp=date_stamp, universe=universe)
        ...

# Wrong — generic factory harder to test, debug, and audit
def make_interaction(survivor_cls, dead_cls): ...
```

**Verify:** Read each file. Is there a concrete class? Does it call `_compute()`
on parent instances directly? Are imports explicit?

### 2. Data Source — fetch_adjusted_ohlcv_rows

All OHLCV-sourced factors must use `fetch_adjusted_ohlcv_rows` from
`app/factors/db.py`, not raw `fetch_ohlcv_rows`.  The raw function returns
unadjusted prices with split jumps.

**N/A for composite factors:** interaction factors that only delegate to
parents (never touch the DB) are fine — the parent factors are already
responsible for their own data access.

**Verify:** grep for `fetch_ohlcv_rows` (without `_adjusted_`) in the factor
file.  If it appears outside a `db.py` import of the adjusted function, flag
it.

### 3. Z-Score Conventions

The standard pattern for interaction factors (Borri et al. 2025): cross-sectional
z-score from parent factors → product → z-score the product.

```python
common = set(parent_a.scores) & set(parent_b.scores)
raw = {t: parent_a.scores[t] * parent_b.scores[t] for t in common}
final = self.zscore(raw)
```

**Verify:** Does the factor compute the product of z-scored signals, then
z-score the result?  Does `self.zscore()` come from `BaseFactor` (static
method, uses `pd.Series`)?

### 4. Registry Registration

Every factor must be imported and registered in `app/factors/registry.py`.

**Verify:**
```bash
cd /d/vesper
grep "import.*$FACTOR_NAME" app/factors/registry.py
grep "$FACTOR_CLASS()" app/factors/registry.py
```
Count the total registered factors and confirm the `_default.register_all()`
call includes the new entries.

### 5. Importability

All factors must import without errors.

**Verify:**
```bash
cd /d/vesper
python -c "
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'deploy')
from app.factors.registry import get_registry
reg = get_registry()
print(f'Registry has {len(reg._factors)} factors')
print(f'Names: {reg.names}')
"
```

### 6. Consistency with Existing Pattern

New factors should follow the same conventions as existing ones.  For
interaction factors, compare against `gv_cb_interaction.py`.

**Checklist:**
- Same `required_data: list[str] = []` declaration
- Same `**kwargs` passthrough on `_compute()`
- Same empty-result guard (`if not a.scores or not b.scores: return FactorResult(scores={}, metadata={"status": "WARNING", ...})`)
- Same metadata structure (`status`, `scored_count`, `source`, `parents`)

### 7. Error Handling

Composite factors must handle missing parent data gracefully.

**Checklist:**
- Empty parent scores → return `FactorResult` with `WARNING` status, not an exception
- Common-ticker intersection may be smaller than either parent — this is fine,
  but should not raise
- `BaseFactor.zscore()` handles zero-standard-deviation edge case (returns zeros)
- Parent factors handle their own DB/data errors (composite factors should not
  duplicate those checks)

### 8. Research Memo / Documentation

Each factor or batch of related factors should have a research memo in
`docs/reports/` documenting economic rationale, methodology reference,
expected effect, and empirical validation plan.

**Verify:** `ls docs/reports/ | grep -i "interaction\|factor-name\|research"`

## GOVERNED_FACTOR_WEIGHTS Drift Check

**Critical:** The `app/services/paper_snapshot_factors.py` file defines
`GOVERNED_FACTOR_WEIGHTS` which is imported by `paper_factor_admission.py`
for governance validation.  If this dict is not updated when new factors are
added to the registry, the admission pipeline will silently ignore the new
factors.

**Verify:**
```bash
cd /d/vesper
# Extract weight keys from both files
python -c "
import re
reg = set()
with open('scripts/run_all_factors.py') as f:
    for line in f:
        m = re.match(r'    \"([a-z_]+)\":', line)
        if m: reg.add(m.group(1))
gov = set()
with open('app/services/paper_snapshot_factors.py') as f:
    for line in f:
        m = re.match(r'    \"([a-z_]+)\":', line)
        if m: gov.add(m.group(1))
drift = reg - gov
if drift:
    print(f'DRIFT: {len(drift)} factor(s) in FACTOR_WEIGHTS but not in GOVERNED_FACTOR_WEIGHTS:')
    for n in sorted(drift): print(f'  - {n}')
    print('Fix: add these to GOVERNED_FACTOR_WEIGHTS in paper_snapshot_factors.py')
else:
    print('OK — no drift')
```

**Fix:** Add the new factors to `GOVERNED_FACTOR_WEIGHTS` in
`app/services/paper_snapshot_factors.py` at weight 0.0 (or their intended
weight).  The `scripts/run_all_factors.py` `FACTOR_WEIGHTS` dict is the
authoritative live-weight source — `GOVERNED_FACTOR_WEIGHTS` is the
admission/governance validation gate.

## Untracked File Check

New factor files often start as untracked git files (`??`).  Before the next
pipeline run, verify they are committed:

```bash
cd /d/vesper && git status --short app/factors/ | grep -v __pycache__
```

If a factor file is untracked but the registry and pipeline config have been
modified to reference it, the factor is importable in a dirty worktree but
will break on a fresh clone.  Commit before the next scheduled pipeline run.

## Outdated Docstring Check

The `registry.py` docstring contains a factor count.  After adding factors,
check if the docstring needs updating:

```bash
cd /d/vesper && head -10 app/factors/registry.py
```

Look for lines like "N factors, M data sources" — bump the count if it's stale.