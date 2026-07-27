# Score Artifact / Universe Gate Audit

## When to Use

Auditing a factor score artifact that may be missing governance fields (`universe`, `universe_size`, `external_factor_tickers_excluded`, `evidence_state`, `factor_outcomes`) or where the S&P 500 universe gate appears not to be filtering correctly.

Common triggers:
- A score file has `scored_count > 502` (S&P 500 size) — non-universe tickers are leaking through
- Governance fields expected by the current `run_all_factors.py` are absent from generated artifacts
- User asks "is the universe gate working?" or "why are scores still showing micro-caps?"

## Diagnostic Sequence

### Step 1: Check what the artifact actually contains

```bash
python -c "
import json
data = json.loads(open('D:/vesper/data/factor_scores_YYYYMMDD.json').read())
print('Keys:', list(data.keys()))
print('scored_count:', data.get('scored_count'))
print('Universe fields present:', all(k in data for k in ['universe','universe_size','external_factor_tickers_excluded','evidence_state','factor_outcomes']))
"
```

### Step 2: Check git history for when the universe gate was added

```bash
cd D:/vesper && git log --oneline -- scripts/run_all_factors.py
```

Look for a commit that introduced `load_scoring_universe`, `scoring_universe`, or `raw_tickers & scoring_universe`. Compare the old version (before that commit):

```bash
git show <PREVIOUS_COMMIT>:scripts/run_all_factors.py | grep -n "universe\|scoring\|all_tickers\|external_ticker"
```

and the current version:

```bash
git show HEAD:scripts/run_all_factors.py | grep -n "universe\|scoring\|universe_path\|scored_count"
```

### Step 3: Determine which version generated each artifact

The artifact's `timestamp` field tells you when it was generated. Compare against the commit date of the universe-gate commit. If all artifact timestamps precede the commit, the gate was added but never exercised.

Check the old version's output format:

```bash
git show <COMMIT_BEFORE_GATE>:scripts/run_all_factors.py | grep -A 30 "output = {"
```

If it lacks `universe`, `evidence_state`, `factor_outcomes`, etc., and the current version has them, that confirms the version-gap hypothesis.

### Step 4: Verify the universe gate WOULD work if run

```bash
python -c "
import json

# Load the score artifact
data = json.loads(open('D:/vesper/data/factor_scores_YYYYMMDD.json').read())

# Load the SP500 universe
with open('D:/vesper/data/sp500_tickers.json') as f:
    sp500 = json.load(f)
sp500_set = set(t.strip() for t in sp500['tickers'].split(','))

scored_set = set(s['ticker'] for s in data['scored'])

print(f'Scored tickers: {len(scored_set)}')
print(f'S&P 500 tickers: {len(sp500_set)}')
print(f'Intersection (would survive universe gate): {len(scored_set & sp500_set)}')
print(f'Non-SP500 tickers (would be excluded): {len(scored_set - sp500_set)}')
print(f'SP500 not in scored (data gap): {len(sp500_set - scored_set)}')
"
```

### Step 5: Verify `sp500_tickers.json` parsing

Confirm `load_scoring_universe()` handles the current file format:

```python
import json, re
with open('D:/vesper/data/sp500_tickers.json') as f:
    payload = json.load(f)
raw = payload.get('tickers') if isinstance(payload, dict) else payload
if isinstance(raw, str):
    members = [part.strip() for part in raw.split(',') if part.strip()]
elif isinstance(raw, list):
    members = [str(part).strip() for part in raw if str(part).strip()]
print(f'{len(members)} unique tickers')
```

The current `run_all_factors.py` `load_scoring_universe()` function (lines 119-140) handles dict-with-string-tickers, dict-with-list-tickers, and bare-list formats. Verify the file matches one of the three branches.

### Step 6: Check for duplicate directories / symlinks

```bash
ls -la D:/vesper/ | grep data
# if data -> vesper_data is a symlink, there's no duplication
stat -c '%i' D:/vesper/data D:/vesper/vesper_data 2>/dev/null
# different inodes is normal for a symlink vs target
md5sum D:/vesper/data/factor_scores_YYYYMMDD.json D:/vesper/vesper_data/factor_scores_YYYYMMDD.json 2>/dev/null
# identical hashes = same file (accessed via symlink)
```

## Common Findings

| Symptom | Root Cause |
|---|---|
| `scored_count > 502` but gate exists in code | Gate was added after last run — artifacts are from old code |
| No `universe`/`evidence_state`/`factor_outcomes` fields | Old script version (pre universe-gate commit) |
| Score files identical in `data/` and `vesper_data/` | `data/` is a symlink to `vesper_data/` — no duplication |
| All 502 S&P 500 members present plus thousands of micro-caps | Informal factors scoring outside S&P 500; universe gate will exclude them on next run |
| `sp500_tickers.json` has `"tickers": "AAPL,MSFT,..."` (string) | `load_scoring_universe()` handles str-branch correctly via split on comma |

## Pitfalls

- **Don't assume missing fields = bug.** The generation script may have been updated since the last run. Always check commit timestamps vs artifact timestamps.
- **Don't assume a gate is working just because it exists in the latest code.** Gates must be *exercised* — a commit adds code, not artifact history.
- **Don't treat `data/` and `vesper_data/` as duplicates.** One is likely a symlink. Verify with `md5sum` or inode comparison.
- **Don't ignore the `timestamp` field.** An artifact from Jul 12 12:06:55 generated with pre-gate code won't magically acquire gate fields on Jul 12 13:26:04 when the commit landed.
- **The `universe_size` field in very old files (Jul 2–5) stores a different value** (ticker count from some earlier subset, like 45 or 493) — not S&P 500 size. Cross-reference against the script version at that time.