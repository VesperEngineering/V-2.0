# Read-only uncommitted-diff drift gate

Use this gate when independently reviewing a working tree that another process or
agent may still own. It establishes candidate identity without printing source or
secret-bearing diff content.

## Candidate identity

A review candidate is the tuple:

- `HEAD` commit
- porcelain-status hash
- binary tracked-diff hash relative to `HEAD` (staged plus unstaged)
- untracked path+content manifest hash

`git diff --check` is an additional whitespace/error gate, not part of candidate
identity and not a substitute for drift detection.

### Expected staged-tree variant

When the user supplies an expected `git write-tree` and asks specifically for the
**staged** candidate, that tree is the authoritative candidate identity. Make its
exact assertion the first repository operation—before status, diff, or tests:

```bash
expected='<tree-id-from-user>'
actual=$(git write-tree) || exit 2
printf 'write-tree=%s\n' "$actual"
test "$actual" = "$expected"
```

Bracket every substantive inspection/test batch with this assertion. Also recheck
immediately after any command or tool failure before correcting and retrying; a
shell-quoting, parser, timeout, or harness failure does not prove the index stayed
unchanged during the failed attempt.

If the observed tree differs, stop even if it later changes back. Record changed
paths without printing source or secrets:

```bash
observed=$(git write-tree)
git diff --name-status "$expected" "$observed"
```

Do not combine results from the two tree IDs. Report staged-tree drift first, then
checks completed on the expected tree, checks aborted, and environment-only facts.
Do not attribute drift to a person or process unless independently proven.

The broader fingerprint below remains appropriate when unstaged and untracked
content are also part of the candidate.

## Deterministic probe

Run from the repository root. The Python block emits hashes only; it does not print
untracked contents.

```bash
set -euo pipefail
printf 'head='; git rev-parse HEAD
printf 'status_sha256='; git -c core.quotepath=false status --porcelain=v1 -z \
  | sha256sum | cut -d' ' -f1
printf 'tracked_diff_sha256='; git diff --no-ext-diff --binary HEAD \
  | sha256sum | cut -d' ' -f1
python - <<'PY'
import hashlib
import os
import subprocess
from pathlib import Path

paths = sorted(
    p for p in subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"]
    ).split(b"\0")
    if p
)
h = hashlib.sha256()
for raw_path in paths:
    h.update(len(raw_path).to_bytes(8, "big"))
    h.update(raw_path)
    path = os.fsdecode(raw_path)
    if os.path.islink(path):
        data = b"L" + os.fsencode(os.readlink(path))
    else:
        data = b"F" + Path(path).read_bytes()
    h.update(len(data).to_bytes(8, "big"))
    h.update(data)
print(f"untracked_count={len(paths)}")
print(f"untracked_manifest_sha256={h.hexdigest()}")
PY
git diff --check HEAD
```

Take two back-to-back probes before reading the diff. Begin only if both candidate
identity tuples match. Re-run after inspection, after every long verification
phase, and immediately before the verdict.

## Read-only test discipline

- Do not stage, stash, reset, format, auto-fix, commit, or invoke test modes that
  rewrite fixtures/goldens.
- Prefer `PYTHONDONTWRITEBYTECODE=1` and pytest `-p no:cacheprovider`.
- Put `--basetemp` outside the repository. If a project test necessarily writes
  tracked or untracked candidate paths, do not run it in the review worktree.
- Capture changed-file stats at the beginning so drift can be summarized without
  exposing patch contents.

## Drift response

Any change in `HEAD`, status hash, tracked-diff hash, or untracked manifest
invalidates the review. Stop immediately; do not silently rebaseline and do not
finish tests against the replacement candidate. A concise report should state:

1. `FAIL — diff changed during review`.
2. Initial and current fingerprints, plus whether `HEAD` changed.
3. Changed-file/stat deltas when available.
4. Whether `git diff --check` passed independently.
5. Which focused tests were not run after drift.
6. That partial inspection produced no approval claim.

A new review may start only after an explicit request to assess the now-stable
candidate. This preserves independence and prevents results from being assembled
across two different diffs.
