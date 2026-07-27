# Read-Only Operator-Terminal Authority Audit

Use this reference for a static/test audit of a terminal or desktop operator surface that claims to be read-only, fail-closed, or authority-closed. It captures the VOT/Tkinter audit pattern without assuming that labels, safe sibling services, or green renderer tests prove the reachable UI graph.

## Core invariant

A read-only claim is true only when **every reachable callback** is read-only. The audit graph is:

```text
visible control / key binding
  -> callback
  -> imported helper
  -> subprocess, database, file, provider, scheduler, approval, or execution boundary
  -> identity + scope + freshness + status gate
  -> checked result / receipt
```

Audit the graph, not the label.

## 1. Freeze the revision and dirty boundary

Before imports or tests:

```bash
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short
git worktree list --porcelain
git diff --quiet HEAD -- <audited-paths>; printf 'scoped_diff_exit=%s\n' "$?"
```

Record whether each audited path is HEAD-equivalent. Repeat the scoped diff after static checks, after tests, and immediately before reporting.

If a target changes during the audit:

1. Do not reset, restore, or overwrite it.
2. Capture `git diff -- <path>` and `git status --porcelain=v2 -- <path>`.
3. Keep the original findings revision-qualified, e.g. `module.py@HEAD:194-239`.
4. Read the candidate, rerun compile/import/Ruff/F821/focused pytest on the changed working tree, and report remaining versus mitigated findings separately.
5. State that the candidate is concurrent/uncommitted; do not silently promote it to canonical.

## 2. Inventory modules, importers, and tests

Start with tracked files so temp trees and worktrees do not pollute the inventory:

```bash
git ls-files 'app/<surface-prefix>*.py' 'tests/test_<surface-prefix>*.py' 'tests/*operator*status*.py'
```

Use AST import mapping across tracked Python files. Important classifications:

- **production importer exists** — reachable library path;
- **test-only importer** — source exists but no tracked runtime caller;
- **no importer + `__main__`** — directly runnable orphan, not strictly dead;
- **no importer and no entry point** — dead candidate;
- **safe service imported only by a legacy/sibling UI** — does not protect the audited UI.

Do not infer coverage from a filename. Search tests for the exact callback/helper names: mutators, redaction loader, missing-source loader, authority computation, identity/scope gate, and error path.

## 3. Trace side effects

Search the audited modules and every imported data/controller helper for:

- `subprocess.run`, `Popen`, shell/CLI wrappers;
- writable database connections and update statements;
- `write_text`, append-mode `open`, `mkdir`, rename/delete;
- scheduler/service/provider calls;
- approval/decision/complete/block/unblock/comment actions;
- hard-coded board names, roots, principals, symbols, accounts, or authors;
- broad exception handlers that turn failures into empty collections;
- returned booleans or receipts ignored by the UI;
- synchronous mutations on the Tk/UI thread.

A CLI used “for audit trail” is still a mutation boundary.

### Safe mutation probe

Never invoke the real CLI. Monkeypatch its process runner in-memory and capture argv:

```python
import target_data_module as data

calls = []

class Result:
    returncode = 0


def fake_run(argv, **kwargs):
    calls.append((argv, kwargs))
    return Result()


data.subprocess.run = fake_run
# If the helper checks executable existence, monkeypatch that check or the
# internal runner rather than creating/calling a real executable.
data.some_mutator("synthetic-id", "synthetic-value")
for argv, kwargs in calls:
    print("ARGV", argv)
    print("KWARGS", kwargs)
```

This proves reachability and exact scope without external side effects.

## 4. Cross-check visible authority

Build a matrix:

| Reachable side effect | Visible authority flag | Authenticated identity | Scope binding | Status/freshness gate | Result checked |
|---|---|---|---|---|---|
| task completion | ? | ? | ? | ? | ? |
| task block/unblock | ? | ? | ? | ? | ? |
| comment/attestation | ? | ? | ? | ? | ? |
| filesystem write | ? | ? | ? | ? | ? |
| broker/order | ? | ? | ? | ? | ? |
| scheduler/provider/model/risk | ? | ? | ? | ? | ? |

Inspect the exact flag list used to derive `AUTHORITY CLOSED`. If a reachable class is absent, the displayed authority state is incomplete even if all listed flags are false.

A hard-coded operator name is a label, not authenticated identity. An approval service that always fails closed is useful only when the GUI callback actually calls it.

## 5. Probe disclosure, not just truncation

Use a temporary synthetic log and run it through the real loader:

```python
import tempfile
from pathlib import Path
import target_data_module as data

with tempfile.TemporaryDirectory(prefix="terminal-log-probe-") as root:
    data.LOG_DIR = Path(root)
    (data.LOG_DIR / "synthetic.log").write_text(
        "PROMPT=SENSITIVE_MARKER\nTOOL_OUTPUT=UNFILTERED_MARKER\n",
        encoding="utf-8",
    )
    output = data.fetch_worker_log("synthetic")
    print("raw_prompt_marker_returned=", "SENSITIVE_MARKER" in output)
    print("raw_tool_marker_returned=", "UNFILTERED_MARKER" in output)
```

ANSI removal, tail reads, byte limits, and character truncation do **not** redact content. Require explicit filtering before the text reaches the widget.

## 6. Probe missing-source truthfulness

Point the data loader at a guaranteed-nonexistent temporary path without creating it. Record whether it:

- raises a sanitized domain error;
- returns an explicit unavailable result; or
- collapses to `[]`/`{}`.

Then trace the UI renderer. Empty data shown as `No active tasks`, `0 active`, or `idle` is false green when the source failed. A raised domain error is only an improvement if the top-level refresh retains the last good snapshot and visibly reports unavailable without raw exception text.

## 7. Identify duplicate paths precisely

For standalone and integrated implementations, record paired method line ranges for build, refresh, cards, details, actions, and process patching. Search for importers and launchers before calling one dead.

Use these labels:

- **active canonical** — board/launcher/runtime caller proves use;
- **directly runnable orphan** — no importer, but has `__main__`;
- **superseded duplicate** — same behavior is embedded in the active path;
- **dead** — no caller, no entry point, no declared future lane;
- **candidate/prototype** — isolated branch/worktree only.

## 8. Minimum focused tests

For a read-only operator surface, require direct tests for:

1. application construction, not only pure render helpers;
2. every visible action callback;
3. denied mutation while authority is closed;
4. authenticated identity and exact board/root/task scope;
5. status-specific button enablement;
6. CLI nonzero exit, timeout, and missing executable;
7. source missing/malformed/locked;
8. last-good snapshot retention;
9. raw log/prompt/credential sentinel redaction;
10. displayed authority state covering every side-effect class;
11. standalone/legacy entry points staying disabled or equivalent;
12. no global process monkeypatch leakage.

Tests of a separate approval ledger are not substitutes for callback tests.

## 9. Non-mutating command matrix

Keep scratch external:

```bash
export PYTHONPYCACHEPREFIX="${TEMP:-/tmp}/operator-audit-pycache-$$"
python -m py_compile <modules-and-focused-tests>
PYTHONDONTWRITEBYTECODE=1 python -c '<import each module and print PASS>'
python -m ruff check --no-cache <canonical-modules>
python -m ruff check --no-cache --select F821 <expanded-audit-scope>
python -m pytest <focused-files-or-nodeids> \
  -q --tb=short -ra -p no:cacheprovider \
  --basetemp="${TEMP:-/tmp}/operator-audit-pytest-$$"
```

Run the narrow canonical suite separately from an expanded adjacent suite. Report focused green and adjacent failures independently; never turn `73 passed, 2 failed` into green. Compare failing expectations with the current board before calling the source wrong—tests can encode retired routes.

## 10. Report structure

1. Revision, branch, initial dirty state, and whether audited paths matched HEAD.
2. Module/test inventory and caller classification.
3. Findings ordered by severity with exact `path:line` or `path@revision:line`.
4. Exact commands and exit/result summaries.
5. Safe probe outputs: captured argv, sentinel disclosure, missing-source result.
6. Focused versus expanded pytest results.
7. Concurrent-drift appendix: candidate diff, rerun gates, mitigated/remaining findings.
8. Final status and an explicit statement of files written by the auditor.

The key conclusion should answer two separate questions: **Does it compile/test?** and **Is its claimed authority posture actually true?** A green static suite cannot answer the second question by itself.
