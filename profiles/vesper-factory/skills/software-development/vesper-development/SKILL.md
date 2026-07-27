---
name: vesper-development
description: Development workflow, concise operator reporting, Hermes asset snapshots, path/data guardrails, and dashboard/tooling patterns for the VESPER 2.0 quantitative trading system.
version: 1.3.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [vesper, v20, workflow, engineering, quant, tkinter]
    related_skills: [surgical-engineering, vesper-factor-workflow, vesper-tkinter-ui-engineering]
---

# Vesper Development

This skill captures cross-cutting development patterns for the `C:\Users\bgonn\Desktop\v20` VESPER 2.0 codebase. It is not a replacement for `vesper-factor-workflow` (factor-specific logic), `vesper-tkinter-ui-engineering` (Tkinter layout), or `surgical-engineering` (general diff discipline) — it bridges them with project-specific workflow conventions.

## Pre-Flight Checklist (Mandatory)

Before editing any code in v20:

1. **Load relevant skills** via `skill_view(name)` — at minimum `vesper-factor-workflow`, `surgical-engineering`, and any domain-specific skill (e.g., `vesper-tkinter-ui-engineering` for dashboard work).
2. **Query the codegraph** via `codegraph_explore()` if `.codegraph/` exists at or above the project root. v20 has its own index (initialized at `C:\Users\bgonn\Desktop\v20\.codegraph`). If CodeGraph warns that results come from a different git worktree, initialize a worktree-local index with `codegraph init -i .` before editing; do not accept source from the other checkout as current evidence. After significant edits, refresh with `codegraph index` (or `codegraph sync` where synchronization is intended), then re-query the changed symbols. `codegraph update` is not a valid reindex command. Keep the generated `.codegraph/` ignored and outside any exact staged path set.
3. **Read `SKILLS/CODE.md` and `SKILLS/EXAMPLES.md`** — these are the project's local coding constitution.
4. **Read `AGENTS.md`** — project-specific authority boundaries, evidence rules, and fail-closed constraints.

Skipping any of these steps risks making changes without understanding the full blast radius, data boundaries, or model assumptions.

## Tool-Call Efficiency for Long Jobs

**Do not burn tool calls polling long-running processes or creating unnecessary temp scripts.** For any job expected to run >10 seconds:

- Use `terminal(background=true, notify_on_complete=true)` — one tool call, runs until finished, pings you with full output.
- If you need live progress, redirect output to a log file and tail it, or have the process write progress to a file you read once at the end.
- Never loop `process(action='poll')` or repeatedly call `terminal()` to check status.
- Prefer direct execution for short verification logic. A temporary script is appropriate when a complex multiline command is rejected by the shell/tool parser or must be deterministically rerun. Put it outside the repository, syntax-check it, execute it once, and remove it after verification.

Example (training script):
```python
# CORRECT — one tool call, one notification
terminal(
    command="python scripts/train_model.py --log-file logs/train.log",
    background=true,
    notify_on_complete=true
)

# WRONG — burns tool calls every few seconds
for _ in range(30):
    process(action='poll')  # DO NOT DO THIS

# EXCEPTION — only when a complex inline command is rejected
write_file(path="<system-temp>/verify.py", content="...")
terminal(command="python <system-temp>/verify.py")
# Remove the temporary file after verification; never leave it in the repo.
```

Example (`--log-file` support in training scripts):
```python
# In train_model.py
parser.add_argument("--log-file", type=Path)
args = parser.parse_args()
if args.log_file:
    fh = logging.FileHandler(args.log_file)
    fh.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    logging.getLogger().addHandler(fh)
```

## Tkinter Dashboard: Live Subprocess Panels

When embedding a long-running subprocess (e.g., model training) inside a Tk dashboard:

1. Launch with `subprocess.Popen(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)` in a background `threading.Thread`.
2. Have the thread read stdout line-by-line and push into a `queue.Queue`.
3. Drain the queue from the Tk main thread via `root.after(200, drain_callback)` — never block the event loop.
4. Insert timestamped lines into a disabled `tk.Text` widget, then re-disable it.
5. Disable the launch button while the thread is alive; re-enable on a `__DONE__` sentinel.

```python
# Background thread
proc = subprocess.Popen([sys.executable, script], stdout=subprocess.PIPE, text=True)
for line in proc.stdout:
    queue.put(line)
queue.put("__DONE__")

# Tk main thread
def drain():
    while True:
        try:
            line = queue.get_nowait()
            if line == "__DONE__":
                btn.config(state="normal")
            else:
                log.insert("end", f"[{ts}] {line}")
                log.see("end")
        except queue.Empty:
            break
    root.after(200, drain)
```

## AGENTS.md as Project Constitution

v20 maintains an `AGENTS.md` at project root that enforces:
- **Pre-flight protocol:** skills + codegraph + CODE.md/EXAMPLES.md before any edit
- **Data boundaries:** never modify `/data` or external data stores (D:/vesper)
- **Execution authority:** explicit denied/allowed lists for what agents may touch
- **Evidence rules:** every claim must be backed by code, config, or explicit assumption

When working in v20, treat `AGENTS.md` as binding. If it conflicts with general guidance, `AGENTS.md` wins for this project.

## Split Adjustment for Price Features

The SP500 OHLCV store (`vesper/data/massive/sp500/sp500_ohlcv.sqlite`) stores **raw** prices. Before computing price-derived features, returns, backtests, or training labels, require the V20-local split-adjustment artifact:

`vesper/data/massive/split_adjustments.json`

Do not use `D:/vesper/vesper_data/split_adjustments.json` or `../vesper_data/split_adjustments.json` as runtime fallbacks. External legacy data may be inspected only for explicitly permitted read-only integrity checks; it must not silently govern V20 execution.

If the V20-local adjustment artifact is missing or unverified, fail closed: do not train or evaluate on raw prices and do not fabricate an artifact. See `references/hermes-local-snapshot.md` for the local-asset snapshot and legacy-path remediation procedure.

A protected data write is permitted only when the user explicitly approves the exact source, destination, code/test slice, and exclusions. Planning approval is not enough. When that gate is granted, use a dedicated worktree if main is dirty or another agent is active, follow vertical RED → GREEN slices, copy bytes without reserialization, verify source/destination/receipt hashes, and obtain independent review. If the session is interrupted, resume by verifying the pending narrow test before stacking another edit; never treat an unexecuted production change as GREEN. Full procedure and a historical example: `references/protected-data-admission.md`.

## Forecast Compatibility and Shadow Portfolio Contracts

For inert forecast and portfolio-target migrations, load both:

- `references/forecast-compatibility-authority.md` for the model-companion authority root;
- `references/shadow-forecast-portfolio-contracts.md` for the exact Observe → Compare → Construct → Plan roadmap sequence, closed schemas, canonical hashing, content-bound targets, reproducible parity receipts, adversarial `dataclasses.replace()` review, and the derivation-closed Step 4 PASS/HOLD protocol.

The key fail-closed rules are:

1. Universe and feature compatibility come from an independently reviewed model-companion manifest, never expected and actual values supplied together by the caller.
2. Portfolio targets embed enough immutable forecast and snapshot content to recompute every digest and reject contradictory public-object replacements.
3. Exact integers and semantic floats use distinct canonical encodings; never coerce ranks/counts to binary64.
4. Forecasts and targets remain opinions/research artifacts without signal, order, risk, execution, broker, promotion, or persistence authority until separately gated.

## Quant Model Training Patterns

### Train-test feature scaling parity (CRITICAL)

If the training pipeline z-scores features cross-sectionally, **inference must apply the exact same z-scoring** or predictions are garbage. A common failure mode:

- Training: `build_training_set()` z-scores features within each date
- Inference: `MLModelStrategy` feeds raw unscaled features to `model.predict()`
- Result: model sees out-of-distribution inputs → random predictions → no trades

**Fix:** In inference, build a panel of all stocks' latest features, run `zscore_features()` on the panel, then predict:

```python
# WRONG — predicts on raw features for each stock individually
for sym, df in data.items():
    feats = compute_features(df)
    pred = model.predict(feats.iloc[[-1]])  # raw scale ≠ training scale

# CORRECT — z-score cross-sectionally before predicting
panel = pd.concat([compute_features(df).iloc[[-1]] for df in data.values()])
zscored = zscore_features(panel[FEATURE_COLS])
for i, sym in enumerate(panel.index):
    pred = model.predict(zscored.iloc[[i]])
```

### Cross-sectional z-scoring

Features must be comparable across stocks and across time. After computing raw features for all stocks, z-score each feature **within each date** (cross-sectionally):

```python
for col in FEATURE_COLS:
    panel[col] = panel.groupby("date", group_keys=False)[col].apply(
        lambda s: (s - s.mean()) / s.std() if s.std() > 0 else 0.0
    )
```

This prevents the model from learning era-specific or stock-specific scale differences.

### Chronological train/test split

Time-series data leaks if you randomize. Always split by date:

```python
cutoff = np.datetime64("2021-01-01")
train_mask = dates < cutoff
test_mask = dates >= cutoff
```

Report **both** train IC and out-of-sample IC. A high train IC with near-zero test IC means overfitting — do not deploy.

### Label construction

For a ranking model, z-score the forward return label cross-sectionally within each date too:

```python
panel["label"] = panel.groupby("date", group_keys=False)["label"].apply(_zscore)
```

This turns the regression target into a relative-ranking signal, which is more robust than raw return prediction.

## Windows-Specific Pitfalls

### `cp1252` default encoding

On Windows, Python's `open()` defaults to `cp1252` (not `utf-8`). Project files containing Unicode characters — em dashes, arrows, smart quotes, non-ASCII symbols — will raise:

```
UnicodeDecodeError: 'charmap' codec can't decode byte 0x90 in position 995:
character maps to <undefined>
```

**Fix:** Always specify `encoding="utf-8"` in `open()` calls that read project files:

```python
# WRONG — fails on Windows if file contains Unicode
with open("config/settings.yaml") as f:
    config = yaml.safe_load(f)

# CORRECT
with open("config/settings.yaml", encoding="utf-8") as f:
    config = yaml.safe_load(f)
```

### CRLF-safe surgical patching

V20 Python files may retain Windows CRLF line endings while patch snippets are expressed
with LF. Repeated fuzzy `old_string` replacements can then match too broadly and consume
a neighboring guard, assertion, or assignment. For insertions or local block changes,
prefer structured patch mode with an `@@ <enclosing function>` context. After every
syntax-sensitive patch:

1. inspect the returned diff for any adjacent deletion not explicitly requested;
2. reread the complete enclosing function before another edit;
3. run `python -m py_compile` with `PYTHONPYCACHEPREFIX` pointed at the authorized external scratch root.

If an unexpected deletion appears, stop and reconstruct the full local block before
stacking another patch. Reread again after the repair: a fuzzy repair can consume the
next line even when the resulting error is only surfaced as an indentation failure.

### External pytest temp paths from Git Bash

When the Windows project interpreter is launched from Hermes' Git Bash/MSYS shell,
passing an MSYS path such as `/c/OB Cyber/...` directly to pytest can be rewritten as
`C:\c\OB Cyber\...`. For required external `tmp_path`/`--basetemp` roots, create the
directory with its MSYS path, but pass a native Windows path to Python and disable
argument conversion for that invocation:

```bash
scratch='/c/OB Cyber/Cyber/Vesper 2.0/Vesper Factory/my-check'
rm -rf "$scratch/basetemp" && mkdir -p "$scratch/tmp"
export MSYS2_ARG_CONV_EXCL='*'
TMP='C:\OB Cyber\Cyber\Vesper 2.0\Vesper Factory\my-check\tmp' \
TEMP='C:\OB Cyber\Cyber\Vesper 2.0\Vesper Factory\my-check\tmp' \
TMPDIR='C:\OB Cyber\Cyber\Vesper 2.0\Vesper Factory\my-check\tmp' \
PYTHONDONTWRITEBYTECODE=1 \
'/c/Users/bgonn/Desktop/v20/.venv/Scripts/python.exe' -m pytest \
  -p no:cacheprovider tests/ \
  '--basetemp=C:\OB Cyber\Cyber\Vesper 2.0\Vesper Factory\my-check\basetemp'
```

A pytest setup error before the test body is not RED evidence. Correct the invocation
and rerun until the intended assertion fails. Remove the entire task-owned scratch root
only after all final verification is complete.

### Explicit RED-tests-only handoffs

When the user explicitly requests a comprehensive tests-only RED candidate for a later
V20 implementation, do not force the ordinary vertical RED → GREEN cycle and do not add
production code merely to make collection proceed. Treat the test file as a bounded
public-contract handoff:

1. Inspect the current production boundary and nearby fixture conventions, but do not
   inspect or reuse a held/unsafe worktree candidate to discover its implementation.
2. Run the exact new test target with the project interpreter and external native
   Windows temp/basetemp. A missing requested module or public API may be the intended
   RED collection result; syntax errors, fixture-import errors, and environment/setup
   failures are not admissible RED evidence.
3. Separately create a fresh `hermes-verify-*` script with `tempfile` under an OS-safe
   temporary directory. Have it parse/compile the test, assert the required contract
   surfaces and exact changed-path scope, and confirm the expected missing production
   boundary. Execute it, preserve its real verdict, remove it, and verify absence.
4. Report the focused pytest result as intentionally RED and the structural verifier as
   ad-hoc verification. Never call the suite green, imply that implementation exists,
   or weaken the tests merely to make collection pass.
5. Keep verifier scripts, pytest scratch, bytecode, caches, and generated artifacts out
   of the repository; cleanup remains a terminal gate even when pytest exits nonzero by
   design.

This is an explicit-user-request exception for contract authoring, not the default V20
implementation workflow.

### Logging format string incompatibility

Python's `%` formatting does NOT support `,` thousands separators. This pattern raises `ValueError: unsupported format character ','`:

```python
# WRONG — % formatting cannot use comma grouping
logger.info("equity=$%,.0f", equity)

# CORRECT — use f-string for locale-aware formatting
logger.info("equity=$%s", f"{equity:,.0f}")
```

## Hermes Asset Snapshots and Legacy Paths

When the user wants Hermes skills, plugins, memory text, profiles, or definitions located under V20, create a **non-runtime, redacted snapshot** rather than moving `HERMES_HOME` or copying the entire application-data tree. Keep credentials, databases, sessions, caches, logs, V1 profiles, source/venv, and reparse points out. Publish with exact hashes and verify that active Hermes remained untouched.

Before replacing an old Vesper path, classify each match as active operation, historical evidence, canonical external data, or snapshot content. Patch active operational paths only by default; do not falsify historical receipts or redirect a real canonical data source merely to remove its text. Full procedure: `references/hermes-local-snapshot.md`.

## Obsidian Planning Boundary

When the user asks for Vesper planning or a Future Vesper design review in Obsidian:

1. Resolve the configured vault and review the full `Vesper 2.0` area before proposing a plan when that broader context is useful.
2. When the user grants the `Vesper 2.0/Vesper Factory` workspace scope, read all of `Vesper 2.0` but create, edit, rename, or delete only inside `Vesper 2.0/Vesper Factory`.
3. Treat every note outside that Factory folder as preserved, read-only research. Do not rename, reorganize, overwrite, or delete it without a new explicit exception.
4. Maintain the assistant's concise append-only working-memory/progress journal in `Vesper 2.0/Vesper Factory/Current Vesper — Carry Forward Map.md`; do not create a competing journal. Record verified facts, inferences, plans, blockers, evidence, and the next gate.
5. Keep plans explicit about **current verified V20 state** versus **future design intent**. A design document or uncommitted worktree is not proof that a feature is implemented or active.
6. State that planning writes do not authorize repository, model, data, configuration, broker, risk, scheduler, or deployment changes. Any later implementation still follows the V20 pre-flight and authority gates.

## Concurrent Factory-Session Protection

When another agent or Codex session is actively building the Factory, treat its Factory worktree as owned and unavailable unless the user explicitly asks for a read-only review of it.

1. Do not edit, test, stage, commit, or otherwise operate inside the active Factory worktree. Work only in the user-authorized Obsidian Factory folder for planning, evidence, and working-memory records.
2. Start adjacent work with a read-only baseline: capture the current main checkout identity/status, model-artifact hashes, relevant data-artifact existence, and declared project boundaries. Preserve any pre-existing dirty state exactly; never repair, stage, or restore it as part of a baseline.
3. For a Python test baseline, target the V20 `tests/` suite explicitly rather than invoking repository-root `pytest`, because a repository may contain unrelated embedded tool/profile tests. Use a temporary root inside the authorized Factory folder, set `PYTHONDONTWRITEBYTECODE=1`, and disable pytest's cache provider.
4. If a test path launches dashboard worker monitoring, task boards, or subprocesses that can observe or collide with the active session, stop that broad run. Re-run only independent core test targets, name the excluded tests, and report the result as a **scoped/partial baseline** — never as a green full suite.
5. Record the baseline, exact verification scope, unverified areas, and next gate in the single Obsidian working-memory journal. Delete only the temporary test artifacts that were created inside the authorized Factory folder.

### Re-ground when another authorized session advances the same gate

A repository can advance between discovery and the first write, especially when another Hermes/Codex session is working autonomously. Treat that as new source-of-truth evidence, not as a branch-name nuisance:

1. Immediately before creating a branch/worktree or dispatching implementation, re-read `git status --short --branch`, `git log`, `git worktree list --porcelain`, and the target branch/worktree status.
2. If the proposed branch or worktree already exists, inspect its HEAD, status, changed paths, and relationship to current `main`; do not delete, reset, reuse, or create a duplicate merely because the original plan expected it to be absent.
3. If current `main` already contains an equivalent cherry-pick under a different commit hash, compare changed paths and a stable patch identity (or inspect the exact diff) before deciding the task is incomplete. Commit-hash inequality alone does not prove missing work.
4. When `main` advanced after the plan was formed, cancel the stale implementation step and re-ground the roadmap in current repository files plus the sole Factory journal. Move to a non-conflicting task such as read-only verification or journal synchronization while the owning session continues.
5. Do not edit, test, stage, or commit inside another session's active worktree. Do not dispatch a second implementation/review for the same gate while an acceptance-critical delegation is already running. Record the collision avoidance explicitly so cancellation is not misreported as task failure.

This prevents duplicate implementations, stale-base reviews, and accidental interference when several approved agents progress the same roadmap concurrently.

## Exact Staged-Candidate Handoffs

When a V20 task begins from an already staged review candidate, subsequent repairs leave
the authorized files as `MM`: the index still contains the superseded candidate while
the worktree contains the new repair. In that state, `git diff --cached` is stale and
must not be presented for review.

1. During RED→GREEN work, inspect `git diff HEAD -- <authorized-paths>` so review covers
   the complete current candidate rather than only the index or only the unstaged delta.
2. Finish focused tests, project tests, syntax checks, and scoped security checks before
   changing the index.
3. Stage only the explicitly authorized paths with `git add -- path/one path/two`; never
   use `git add -A` for an exact-path handoff.
4. Require all of the following before reporting “ready for independent review”:
   - `git diff --name-only` is empty;
   - `git diff --cached --name-only` equals the declared path set exactly;
   - `git status --short` shows index-only modifications for those paths and no untracked files;
   - the staged diff, tree identity, and any requested staged binary-diff hash were computed
     from the final index, not from the earlier baseline.
5. Reproduce a declared staged-diff hash with the **exact hashing command that defined it**.
   For the normal V20 handoff convention use
   `git diff --cached --binary | sha256sum`; adding `--full-index` changes the byte stream
   and therefore the hash even when the staged candidate is unchanged. If both forms are useful,
   label them separately rather than treating their differing hashes as candidate drift.
6. Recheck branch, HEAD, staged tree, staged paths, unstaged paths, untracked paths, and the
   canonical staged-diff hash after all review tests and after deleting external verifier scratch.

If tool or time limits interrupt before this checkpoint, report the candidate as focused-green
but **not staged/review-ready**. Do not blur implementation success with handoff completion.

## Fail-Closed Research Evaluators

For phase-gated or holdout-gated evaluators, use a single atomic outcome entrypoint rather than a public verify/mint/evaluate sequence. Authorization must bind the raw contract, phase, evaluator, database, partitions, and final authority before loading inputs; the evaluator must re-hash mutable bindings before returning results. Do not treat module globals, underscore classes, reusable contexts, or closure capabilities as a security boundary.

If a genuine external final-approval root does not exist, keep final outcome computation unavailable even when a caller can construct a self-consistent local manifest. Integrity-only paths may return counts and binding status but must not return rows, blocks, labels, or outcome helpers. After any evaluator-hash change, preserve prior receipts as historical evidence and create explicit versioned superseding contracts/receipts rather than silently rebinding old evidence.

See `references/fail-closed-research-evaluators.md` for the atomic API pattern, required RED regressions, adversarial review boundary, TOCTOU checks, and evidence-rebinding procedure.

## Contract Authority Roots

Fail-closed provenance checks require an authority root independent of the per-call request. Never treat `caller_actual == caller_expected`, a caller-supplied approved universe, or a self-sealed manifest as authorization. Bind model/feature/universe/horizon compatibility in a separately frozen and independently reviewed manifest, detached signature, or equivalent external root. Per-run calls may supply changing dataset/run identities, but they may not self-approve model compatibility.

For shadow forecasts, prefer a model-companion compatibility manifest that binds exact model bytes, ordered feature schema, approved universe, horizon, and target definition. Load and validate it inside the forecast path; reject model, feature, universe, or manifest drift. See `references/contract-authority-roots.md` for the reusable design, atomic outcome boundary, and RED regression checklist.

## Reproducible Research Receipts

A derived-data or run-manifest hash is not independently verifiable unless the receipt specifies the exact byte stream and canonicalization that produced it. Record row windows/order, columns/types, timestamp and float serialization, framing/separators, encoding, counts, and expected digest. Embed the complete run-manifest plus canonicalization/canonical JSON, or bind an exact immutable artifact path and raw hash.

On Windows, review receipt hashes against exact staged blobs rather than CRLF-translated worktree bytes. If a numerical/parity result passes but its receipt is under-specified, preserve the result, issue an explicit receipt revision, add the missing reproducibility contract, refreeze the staged identity, and obtain a fresh independent review. For the full recipe and checklist, load `references/reproducible-research-receipts.md`.

## User-Facing Reporting

For this user's VESPER work, default to a minimal completion report:

- **Result:** what is now true.
- **Evidence:** the single most important real verification result.
- **Blocker or next step:** include only when one exists.

Keep routine reports to roughly 1–4 short bullets. Do not narrate tool calls, reproduce long logs, or dump every technical detail unless the user asks.

For VESPER work that remains active longer than roughly 30 seconds, provide concise progress updates when the platform/session permits. Each update should name the current implementation or review stage, the latest completed evidence, and the next gate. When the user asks which stage is active, map the engineering label to the exact roadmap location when available — Obsidian file, section heading, and numbered migration step — instead of answering only with an internal term such as “candidate freeze.” Do not promise automatic periodic delivery when a background process cannot push updates; report promptly when a result or user check-in arrives.

If work fails, state the exact failure and what remains in plain language; offer deeper detail rather than front-loading it.

If the user says the explanation is overwhelming or asks to start over, stop the technical narrative immediately. State the safety/current state in one sentence, present at most one decision with no more than three choices, and do not resume the prior implementation until the user chooses. A reset request is a workflow reset, not an invitation to summarize the same detail again.

## Verification Checklist

- [ ] Loaded relevant skills before editing
- [ ] Queried codegraph for blast radius; used a worktree-local index when CodeGraph identified another checkout
- [ ] Rechecked main/branch/worktree identities immediately before implementation and avoided duplicating any concurrent accepted gate
- [ ] Re-indexed significant edits with `codegraph index`/`codegraph sync`, not `codegraph update`
- [ ] CRLF-sensitive patches were followed by enclosing-block inspection and external-pycache syntax compilation
- [ ] Git Bash pytest runs used native Windows temp/basetemp paths with MSYS conversion disabled when required
- [ ] Exact review handoffs have no unstaged delta and exactly the declared staged paths
- [ ] Read CODE.md, EXAMPLES.md, and AGENTS.md
- [ ] Long jobs use `background=true, notify_on_complete=true`
- [ ] Dashboard subprocess uses thread + queue + `after()`, not blocking calls
- [ ] Windows file reads specify `encoding="utf-8"`
- [ ] Logging uses f-strings (not `%` formatting) for comma-grouped numbers
- [ ] V20-local split adjustment is verified before price features/training; no legacy fallback or raw-price continuation
- [ ] Hermes snapshots are non-runtime, redacted, hash-manifested, and exclude secrets/databases/V1 profiles
- [ ] Legacy-path edits distinguish active operations from historical evidence and canonical data references
- [ ] Chronological train/test split used for time-series model evaluation
- [ ] Cross-sectional z-scoring applied to both features and labels
- [ ] Inference z-scoring matches training z-scoring exactly
