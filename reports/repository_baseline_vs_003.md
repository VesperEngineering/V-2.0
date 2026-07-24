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

Pending initial commit at report-draft time. This section is finalized after the
explicit staging inspection and initial `master` commit.

## VS-002 repair record

Pending initial commit. The guarded repair will use only `git -C
C:/Users/bgonn/Desktop/v20/.worktrees/cool-sage reset --hard <baseline-sha>` and
will be followed by matching-HEAD, required-path, and clean-status checks.

## Verification results

Pending initial commit. The baseline regression intentionally requires a
resolvable `HEAD` and will run only after commit creation. No lint, typecheck,
or build command is declared by this repository; those gates are unavailable and
are not invented.
