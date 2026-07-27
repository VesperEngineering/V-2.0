# Source-Faithful Autoresearch Adaptation and Codex Verification

Use this reference when adapting a fixed-budget, agent-driven training repository to a new domain.

## Upstream contract

Verified against `karpathy/autoresearch` commit `228791fb499afffb54b46200aca536f79142f117`:

- It is a task-specific example, not a reusable orchestration library.
- `prepare.py` owns fixed data preparation and evaluation utilities.
- `train.py` is the only experiment file the agent edits.
- `program.md` is the human-authored contract for an external agent.
- Codex/Claude is the autonomous loop; the repo has no generic agent runner, `src/` package, or autonomous-loop CLI.

## Faithful adaptation

Clearly label any domain adaptation as custom; never present it as upstream procedure.

1. Inspect the upstream README, manifest, `prepare.py`, `train.py`, and `program.md` directly.
2. Create a fresh isolated template clone or reproduce the three-file contract in the target repository.
3. Replace the task-specific contents with:
   - fixed domain-specific `prepare.py` / evaluator;
   - editable domain-specific `train.py`;
   - human-reviewed domain-specific `program.md`;
   - domain dependencies.
4. Review and manually exercise one baseline before unattended execution.
5. During research, the external AI agent must propose and edit `train.py`; a Python loop rotating a hardcoded mutation table is a parameter sweep, not the upstream agent-driven method.
6. Keep data, evaluator, split, metric, seed policy, and wall-clock budget immutable.

## Validate the frozen data contract before authoring the program

Do not write the target/evaluator specification from assumptions about the source system. Enumerate the copied files, inspect schemas and date/symbol coverage, and distinguish available fields from desired fields before freezing the control document.

A finance adaptation in this workflow exposed two useful examples:

- No separate ticker-list or sector-map file existed, so the usable universe had to be derived from the intersection of OHLCV symbols and point-in-time membership rather than inventing an input.
- OHLCV plus split adjustments did not contain dividend or delisting distributions, so a 21-session split-adjusted close-to-close **price-return proxy** was supportable, but a total-return claim was not.

Encode limitations directly in the program and result labels (for example, `survivor-cohort-limited` and `price-return-proxy`). Require the bootstrap agent to report actual schema, coverage, observation counts, and missing capabilities before it replaces files or runs a baseline.

## Program-file adaptation scope

The upstream structure can remain source-faithful even when most task-specific prose changes. A GPT-oriented `program.md` may embed tokenizer, cache, metric, output, and lower-is-better assumptions throughout; a finance or other domain port therefore often requires a full rewrite rather than scattered substitutions.

- Say this early and accurately. Do not describe a near-total rewrite as “targeted edits.”
- Preserve upstream `program.md` unchanged.
- Author a separate domain file such as `program.<domain>.md` and point the external agent to that exact file.
- Keep the conceptual contract: fixed preparation/evaluation, one editable training file after bootstrap, fixed time budget, result ledger, Git keep/revert loop, and human stop control.
- If the adaptation needs a one-time bootstrap that may replace `prepare.py`, `train.py`, and dependencies, distinguish that temporary permission from the steady-state rule that only `train.py` is editable.

When the user requests the complete Markdown source, deliver an actual `.md` artifact whenever possible. Chat rendering and nested fences can hide literal `#` headings, terminate an outer fence, or turn intended tab characters into `\\t`. Read the complete artifact back, correct literal-versus-escaped characters, compute a SHA-256, and provide one copy command plus the expected hash.

## Codex CLI preflight

Never rely on remembered flags. Verify the installed interface first:

```bash
codex --version
codex --help
codex exec --help
```

In `codex-cli 0.144.5`, `--full-auto` was absent. The verified interactive form was:

```bash
codex --cd "$WORKSPACE" --ask-for-approval never --sandbox workspace-write
```

Wait until the Codex TUI is visibly open before pasting a multiline prompt. If startup fails, prose pasted at a Bash prompt is interpreted as shell commands.

## GPU/sandbox preflight

CUDA visible in the user's shell is not proof that it is visible inside Codex's effective sandbox. Before an overnight run, execute a bounded probe through the exact interpreter and sandbox that will launch training. Record:

- absolute `sys.executable` and argv;
- Codex version and sandbox mode;
- PyTorch/CUDA versions;
- `torch.cuda.is_available()` and device name;
- runtime/VRAM;
- full traceback on failure.

A Bubblewrap fallback warning is not itself a failure, but it is not evidence of GPU exposure. A receipt containing only `CUDA_REQUIRED` without interpreter, command, environment, and traceback is insufficient.

## Isolation and audit

- Put required directory-navigation commands first.
- Use a distinct WSL-native workspace and copied/frozen data; do not grant a common ancestor containing production and research repos.
- Record source commit and data hashes before adaptation.
- Check `git status --short --untracked-files=all` before and after Codex.
- Preserve failed generated work in quarantine until audited.
- Distinguish verified source facts, custom design decisions, and unknowns. Never fill gaps with plausible assumptions.
