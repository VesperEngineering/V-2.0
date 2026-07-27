# Strict Read-Only Audit of a Non-Git Source Bundle

Use this when the target is a copied folder, source archive, prototype bundle, or extracted release rather than a Git worktree, and the user forbids all mutation.

## 1. Freeze before inspection

Do this **before** imports, tests, linters, application startup, or any command that could create caches:

1. Prove the path exists and record its canonical path.
2. Record top-level names.
3. Record whether `.git` exists. If it does not, state that history, provenance, branch state, and prior exposure cannot be verified.
4. Produce a deterministic manifest with:
   - file count and total bytes;
   - content hash over relative path + bytes;
   - metadata hash over relative path + size + `mtime_ns`;
   - explicit exclusion list for dependency trees such as `.venv`, `venv`, `node_modules`, and `.git`.
5. Inventory volatile artifacts (`__pycache__`, `data`, `logs`, coverage output) separately. Do not silently exclude them from the no-touch proof.

Use `scripts/source_manifest.py` for the baseline and repeat the exact command at the end.

## 2. Static-only inspection ladder

When the boundary forbids mutation:

- Read text files directly; never import project modules.
- Parse Python with `ast.parse` or `compile(source, path, "exec")`; do not use `py_compile`, which writes bytecode.
- Do not run tests, formatters, linters with caches, installers, setup commands, application entrypoints, or constructors that create state directories/databases/logs.
- If normal file search returns an implausible empty result on a Windows path, verify with a bounded `os.walk`, pruning dependency, VCS, cache, generated, data, and artifact trees. This is a path-resolution check, not evidence that the repository is empty.
- Do not use dependency-directory contents as application evidence unless the audit explicitly covers supply-chain state.

## 3. Build a contradiction matrix

For small systems, configuration/documentation drift often matters more than code complexity. Compare:

| Claim surface | Verify against |
|---|---|
| README/run instructions | Existing entrypoint, imported symbols, startup sequence |
| Architecture inventory | Actual files and callable implementations |
| Config provider/strategy/mode | Factory-supported values and case sensitivity |
| Config knobs | Runtime consumers; mark declared-but-unused keys |
| Safety mode/banner | Actual side-effect client and endpoint selection |
| Feature/model settings | Model artifact, training producer, required history, runtime interface |
| Cache/audit/state claims | Reachable readers/writers and integrity semantics |
| Tests | Exact critical paths and failure modes covered |

Trace the **blocker ladder** for each advertised entrypoint: first import blocker → first construction blocker → first configuration blocker → first missing artifact → first side-effect boundary. A later blocker does not erase an earlier one.

## 4. Trading and other side-effecting systems

For systems capable of financial, deployment, messaging, or account mutation:

1. Separate the displayed mode from the effective client/endpoint/credential mode.
2. Require unavailable external state to be represented as `unknown/error`, never as a valid empty collection.
3. Trace closing/rollback/recovery actions through request, tracking, terminal confirmation, retry/escalation, and only then state clearing.
4. Treat policy comments and governance YAML as declarations until an execution-capable function enforces them.
5. Inspect credential-shaped material by file, line, and variable/key name only. Never reproduce values. Recommend rotation conditionally when validity cannot be established.

## 5. End verification

Repeat the baseline manifest with identical exclusions and compare every field. Also confirm:

- no new top-level directories;
- no new `data`, `logs`, coverage, model, or receipt artifacts;
- no new or changed bytecode caches;
- no changed source/config/document files.

If the baseline was captured late, say so. Do not present a mid-audit hash as proof covering earlier steps. A strong conclusion is: `No changes detected during the measured verification window`; a stronger whole-session claim requires a true pre-inspection baseline.

## Report posture

Lead with the maturity verdict and the first executable blocker. Distinguish:

- **current blocker** — prevents the checked-in path from running now;
- **latent safety defect** — dangerous if a later configuration or wiring change activates it;
- **readiness gap** — tests, reproducibility, observability, or documentation debt;
- **unverified** — cannot be proven without execution or external authority.

End with the smallest safe remediation order, not a wholesale rewrite.