# VS-003 Repository Baseline Restoration

## Scope and assumptions

This report records restoration of the existing untracked VESPER checkout as Git's
first reviewed baseline. The work is limited to repository metadata and the
intentional review surface; it does not invoke trading, providers, brokers, or
schedulers. It does not alter risk/trading settings, model artifact bytes, or
protected data/research directories.

Assumptions verified during preflight:

- The primary worktree at `C:/Users/bgonn/Desktop/v20` is the intended `master`
  checkout containing the complete untracked VESPER source.
- The `fusion/vs-002` worktree is exactly the record whose porcelain branch is
  `refs/heads/fusion/vs-002`; it was empty except for its `.git` pointer and had
  clean index and worktree state, so it may safely be populated only after the
  baseline commit exists.
- No CodeGraph exploration tool is available in this execution environment; the
  existing CodeGraph state is deliberately ignored rather than modified.
- The available skill search found a relevant Git leak-recovery skill, but its
  installation failed before any project mutation. The repository's `SKILLS`
  governance documents were read and applied.

## Original symptom evidence

At the primary root before mutation:

- `git status --short --branch`: `## No commits yet on master`
- `git rev-parse --verify HEAD`: failed with `Needed a single revision`
- `git ls-files | wc -l`: `0`
- `git remote -v`: no output (no configured remote)
- `git worktree list --porcelain`: primary `master`, this VS-003 worktree, and
  `fusion/vs-002` all reported an all-zero `HEAD`.

The VS-002 record resolved to
`C:/Users/bgonn/Desktop/v20/.worktrees/cool-sage`. Before any reset it reported
`## No commits yet on fusion/vs-002`, had no project files, and both `git diff
--quiet` and `git diff --cached --quiet` succeeded.

## Classification manifest

### Tracked intentional review surface

- Root documentation and setup: `AGENTS.md`, `README.md`, `architecture.txt`,
  `requirements.txt`, `.env.example`, and `.gitignore`.
- Declared configuration, unchanged: `config/settings.yaml` and
  `config/universe.yaml`.
- Project guidance, assets, source, scripts, tests, reports, and model evidence:
  `SKILLS/`, `assets/`, `vesper/` excluding protected data/research, `scripts/`,
  `tests/`, `reports/`, `models/xgb_ranker.json`, and
  `models/xgb_ranker.metadata.json`.

### Ignored local/runtime/protected material

- `.env`: local credentials; never read or staged.
- `.venv/`, `venv/`, Python bytecode, packaging output, test caches/temp paths,
  databases, `data/`, and `logs/`: machine-local dependencies, generated output,
  or runtime state.
- `.fusion/`, `.codegraph/`, `.hermes/`, and `.worktrees/`: daemon/index/tooling
  state and linked-worktree storage, not portable project source.
- `hermes-local/` and `quant workers/`: local operator/tooling materials outside
  the runnable VESPER review surface.
- `IGNORE RUN.txt`: local operator scratch/instructions rather than canonical
  repository documentation.
- `vesper/data/massive/` and `vesper/data/model_research/`: protected read-only
  provider data and research artifacts, explicitly excluded by project policy.

`.env.example` was scanned without disclosing values. Its prior non-placeholder
credential-like samples were replaced only with inert `replace_with_*`
placeholders before staging. `.env` was neither opened nor staged.

## Staging and commit evidence

The explicit staging set contained **177 files** and was inspected with `git diff
--cached --name-status`. It contained the classified source, configuration,
models, reports, tests, assets, and documentation only. A forbidden-path check
found no `.env`, virtualenv, Fusion/Hermes/CodeGraph state, pytest state,
worktree state, local operator directories, protected data/research paths,
databases, or bytecode in the index.

Initial baseline commit:

- SHA: `01d06f2f56fabd5b78eab4a7b9d7b86f02c1700f`
- Message: `feat(VS-003): establish reviewed VESPER repository baseline`
- Tree inventory: 177 tracked files, 17,018 inserted lines.

The staged-text credential scan found only the sanitized `.env.example`,
environment-variable references, code identifiers, and test references; it found
no credential value to disclose. `git diff --cached --check` reported 129
pre-existing whitespace diagnostics in preserved input documentation and one
pre-existing blank line at EOF in `vesper/dashboard/worker_monitor.py`. They
were not normalized because this restoration is required to preserve the
existing review surface rather than make unrelated source/doc edits.

## VS-002 repair record

After the required clean/empty guard, the linked worktree was populated only
with:

```text
git -C C:/Users/bgonn/Desktop/v20/.worktrees/cool-sage reset --hard \
  01d06f2f56fabd5b78eab4a7b9d7b86f02c1700f
```

Both root `master` and `fusion/vs-002` then resolved to
`01d06f2f56fabd5b78eab4a7b9d7b86f02c1700f`, had 177 tracked files, and had
clean status/diff results. The repaired worktree contains `AGENTS.md`,
`SKILLS/CODE.md`, `tests/test_risk.py`, and `reports/`.

## Verification results

All executed checks passed against the initial baseline:

- `tests/test_repository_baseline.py`: **2 passed** in 0.33s using the README
  Windows temporary-directory environment.
- `tests/test_risk.py`: **5 passed** in 1.79s using the same environment.
- `.venv\Scripts\python.exe -m py_compile tests\test_repository_baseline.py
  vesper\engine.py`: passed.
- Root/VS-002 `git rev-parse --verify HEAD`, required tracked-path checks,
  `git ls-files`, worktree porcelain, clean status, and clean `git diff HEAD`:
  passed; both no longer have unborn/all-zero heads or zero tracked files.
- `git check-ignore -v` confirmed `.env`, `.venv`, `.fusion`, `.codegraph`,
  `.pytest_tmp`, `.worktrees`, and both protected VESPER data/research paths
  are ignored by the documented `.gitignore` rules.

No lint, typecheck, or build command is declared by this repository, so those
gates are unavailable and were not invented. No broker, provider, scheduler,
trading path, protected data/research file, risk/trading setting, model artifact
content, or credential file was modified.
