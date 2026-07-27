# Autonomous Research Repository Adaptation

## Classify before setup

Before telling a user how to apply an autonomous-research repository to another domain, inspect the current upstream source and classify the intended use explicitly:

1. **Run upstream as written** — use its included model, data, metric, and instructions.
2. **Use upstream as a template** — fork/copy its scaffold, then replace domain-specific files.
3. **Recreate the pattern elsewhere** — build an analogous harness in the target project with no runtime dependency on upstream.

Do not present option 3 as the upstream repository's documented procedure. If the user expects to use the original repo, pause before launching an agent and explain the distinction.

## Karpathy autoresearch structural audit

Audited `karpathy/autoresearch` master at commit `228791fb499afffb54b46200aca536f79142f117`.

It contains ten tracked files and no `setup.py`, `src/`, `__init__.py`, generic agent runner, or orchestration CLI. Its operative contract is:

- `prepare.py`: fixed LLM data preparation and evaluation.
- `train.py`: GPT model and training loop edited by the agent.
- `program.md`: instructions consumed by an external coding agent.
- Git/results ledger: keep or revert experiment state.

The autonomous loop lives in the external agent behavior described by `program.md`; the repository is a self-contained LLM experiment and reference design, not a reusable framework package. Applying it to finance or another domain requires replacing or recreating the data preparation, editable trainer/model, metric, and program instructions.

## Source-faithful template ports

A domain port has two distinct phases:

1. **Bootstrap:** replace the domain-specific fixed data/evaluation surface, baseline editable trainer, and dependencies; inspect the exact diff and run bounded protocol/CUDA checks.
2. **Research:** freeze the bootstrap surfaces and let the external coding agent edit only the declared experiment file under the human-authored instruction contract.

Do not call a generated harness source-faithful merely because its filenames resemble upstream. Inspect who owns the loop. A `loop.py` containing a fixed `MUTATIONS` list or round-robin parameter choices is a grid runner, not Karpathy’s external-agent research loop. The instruction file should direct the external agent to propose one hypothesis, edit the experiment file, commit, run, log, keep/revert, and repeat.

When collaborating with a user on the human-authored instruction file, fetch/read the exact upstream revision yourself. Do not require them to copy a long nano/terminal transcript. Preserve the upstream file, make a separate review copy, and inspect a diff before replacement. If they prefer a GUI from WSL, `notepad.exe "$(wslpath -w program.review.md)"` opens the WSL-native review file in Windows Notepad.

For long Markdown contracts with nested code fences, exact hashes, or tab-delimited examples, do not rely on chat rendering. Create an actual `.md` file in a host path visible to WSL, read the entire file back, correct escaped literals such as `\\t` when real tabs are intended, compute its SHA-256, and provide one copy command into the isolated repository. Keep the upstream control file untouched and activate only the separately reviewed domain copy (for example `program.<domain>.md`).

## GPU and receipt proof

A host-shell CUDA check does not prove that the same interpreter inside the coding-agent sandbox can see the GPU. Before an overnight run, capture the exact launch command and run the CUDA probe with the exact interpreter and permission profile that will launch training.

For Codex on WSL2, first satisfy the official sandbox prerequisite and verify the installed CLI syntax:

```bash
sudo apt install -y bubblewrap
bwrap --version
codex sandbox --help
```

Then compare WSL GPU visibility outside and inside the Codex sandbox before involving PyTorch:

```bash
nvidia-smi --query-gpu=name --format=csv,noheader
codex sandbox -C "$WORKSPACE" -- sh -lc 'printf "dxg="; if test -e /dev/dxg; then echo present; else echo missing; fi; nvidia-smi --query-gpu=name --format=csv,noheader'
```

Installing Bubblewrap improves sandbox reliability but does not itself prove GPU visibility; only the same-command probe does. After the device probe, verify CUDA with the exact Python interpreter that will launch training. Record at minimum:

- `sys.executable`
- Python and PyTorch versions
- `torch.cuda.is_available()`
- CUDA device name
- sandbox/approval mode
- exact training command

A failed receipt containing only `CUDA_REQUIRED` is insufficient to diagnose cause. Receipts must also include command, interpreter, environment identity, exit code, and traceback. Distinguish wrong-interpreter failures from sandbox/device-visibility failures before changing sandbox policy.

## Codex shell/TUI boundary

Before giving a long agent prompt:

1. Run `codex --help` for the installed version; legacy flags may disappear.
2. Launch Codex with syntax verified from that output.
3. Wait until the Codex TUI input interface is visibly open.
4. Only then paste the natural-language prompt.

If prompt headings or Markdown bullets produce shell errors such as `Command 'Build' not found`, Codex did not open and the prompt was pasted into Bash. Stop immediately and relaunch correctly.

For Codex CLI 0.144.5, the verified interactive unattended-workspace form is:

```bash
codex --cd "$WORKSPACE" --ask-for-approval never --sandbox workspace-write
```

Treat this as version-specific and re-check `codex --help` on later releases.