---
name: autonomous-gpu-research
description: Safely bring fixed-budget, agent-driven ML research repositories up on local GPU hardware, including WSL2/CUDA validation, dataset preparation, memory sizing, kernel compatibility, reproducible experiment loops, and human-readable troubleshooting.
---

# Autonomous GPU Research

## Trigger

Use when a user wants to run or adapt an autonomous ML-research repository locally, especially a single-GPU training loop with an agent modifying model code and keeping/discarding experiments.

## Operating principles

1. **Inspect before modifying.** Read the original repository README, dependency manifest, fixed data/evaluation code, editable training code, and agent instructions with tools. Identify the authoritative metric, immutable files, and exact source commit.
2. **Separate source procedure from adaptation.** State explicitly whether a step comes from upstream documentation or is a custom domain adaptation. Never describe a custom scaffold as though upstream prescribed it.
3. **Verify the agent CLI.** Run the installed agent's `--version` and relevant `--help` commands before prescribing flags. Wait until the agent UI is visibly open before the user pastes a multiline prompt.
4. **Separate environments explicitly.** Windows terminals and WSL2 terminals are different execution environments. GPU checks, dependency sync, data caches, and training must all occur in the same WSL2/Linux environment.
5. **Validate the effective device path.** Check CUDA from both the project environment and the exact agent sandbox/interpreter that will launch training; shell-level CUDA success does not prove sandbox visibility.
6. **Start conservatively.** Estimate model, activation, and optimizer memory. On a smaller GPU, reduce sequence length, per-device batch size, model depth, and possibly total batch size before the first run. Keep one change at a time and record it.
7. **Preserve the benchmark.** Do not alter the evaluation harness or fixed data constants unless the project explicitly permits it. If reducing context/evaluation size for hardware, label the result as a local baseline and do not compare it directly with upstream runs.
8. **Treat custom kernels as hardware-specific.** If a Flash Attention/custom kernel reports `no kernel image is available for execution on the device`, replace it with a supported PyTorch implementation only after checking tensor layout and causal/window semantics. For a full-window baseline, PyTorch SDPA is an appropriate fallback; document that it may be slower and may not preserve sliding-window behavior.
9. **Use verifiable, surgical edits—but describe scope honestly.** Prefer exact patches or an editor with clearly identified blocks. If a domain port changes nearly every task-specific instruction, call it a full rewrite of a separate adaptation file, not a “targeted edit.” Preserve the upstream file unchanged for audit and diff.
10. **Deliver literal control files as files.** When Markdown/TOML contains headings, hashes, tabs, or nested fences, create an actual artifact instead of relying on rendered chat. Verify the complete file, correct escaped-vs-literal tabs, compute a SHA-256, and have the user copy only the verified artifact into the workspace.
11. **Require a complete baseline receipt.** Capture the absolute interpreter, argv, agent/sandbox mode, metric, training time, peak VRAM, steps/tokens, parameter count, configuration, source/data/evaluator hashes, and full traceback on failure.

## Fixed-Budget Rented GPU Decisions

Before using a temporary GPU rental, separate three questions:

1. **Is the model hypothesis viable?** A larger architecture or an existing checkpoint is not enough. Require a concrete economic hypothesis, available or point-in-time-valid data, leakage-controlled chronological evaluation, a fixed baseline/control, and cost-aware economic metrics.
2. **Which provider is being compared?** “GPU alternatives” can mean alternate model architectures, alternate hardware, or alternatives to a named provider such as RunPod. When a named provider is mentioned, compare providers rather than redirecting into non-GPU alternatives.
3. **What can be charged?** Verify active-compute billing separately from stopped-instance, persistent-volume, egress, reservation, or subscription charges. Fixed credit does not authorize an unbounded sweep.

For an approved provider comparison, lock one immutable experiment archive: source/data/evaluator hashes, seed, deadline, and stop criteria. Run it at most once per provider; do not tune between providers or count the two runs as independent model validation. Export receipts and destroy the instance plus unneeded paid volumes promptly.

### Project-local credentials

If a user explicitly asks for provider credentials to live in a project, inspect the project’s existing secret loader first. Reuse an established local `.env` convention when present; do not invent a second secret path. Keep credentials out of source, reports, model metadata, logs, command arguments, and durable memory. On Windows, restrict the resulting credential-file ACL to the operating user plus required system/administrator principals, then verify only file existence, variable names, value lengths, and ACLs—not secret values.

## Standard workflow

1. Confirm hardware and environment in the same shell:
   ```bash
   nvidia-smi
   uv run python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0)); print(torch.cuda.get_device_capability())"
   ```
2. Keep the repository on the WSL2 filesystem (`~/...`), not `/mnt/c/...`, for training workloads.
3. Run `uv sync`; use `uv run ...` rather than system-wide `pip` in externally managed Ubuntu environments.
4. Inspect and adjust only the documented hardware knobs. Verify the diff and run `uv run python -m py_compile train.py`.
5. Run data preparation once and verify the expected cache/tokenizer exists.
6. Run one baseline manually before autonomous iteration. Redirect long logs to a file when the project instructions require it.
7. Before autonomous mode, verify the installed agent CLI syntax and run bounded CUDA **and patch-path** probes through the exact sandbox and interpreter the agent will use. On WSL2, test `/dev/dxg`, `nvidia-smi`, and a harmless workspace create/patch/delete operation through the same effective boundary; a GPU-only probe can pass while later patch metadata setup fails. Record what remains technically enforced (write isolation, read denial, network denial) versus merely instructed by the program file.
8. Create a fresh experiment branch, initialize an untracked results file, and give the external agent the repository's human-reviewed program/instructions file. Preserve the untouched upstream program alongside a domain-specific adaptation when most semantics change. For autoresearch-style work, the agent must edit the designated training file; do not substitute a hardcoded mutation loop while calling it agent-driven research.
9. Stop on crashes, OOM, timeout, metric corruption, missing provenance, or an unverified result; do not silently convert a failed run into a success.

## WSL2 memory accounting during active research

When Task Manager shows substantial `VmmemWSL` memory, do not infer a leak from that number alone. First identify the active Linux worker and split the VM working set into process RSS, reclaimable cache, and WSL/runtime overhead. The WSL `memory=` setting is a ceiling, while `autoMemoryReclaim=gradual` returns cache gradually and cannot reclaim live Python/PyTorch allocations. A persistent `vmIdleTimeout=-1` intentionally keeps the VM and warm cache alive after work completes.

Collect host availability, guest `free`/`meminfo`, top Linux RSS/CPU processes, and GPU activity before recommending a cap change or shutdown. Treat an active high-RSS training worker with meaningful CPU/GPU utilization and available host RAM as normal. Investigate only monotonic growth across completed runs, unexplained resident usage, cap/OOM events, or Windows paging/freezing. Never run `wsl --shutdown` or cache-dropping commands during active research without explicit approval; they trade current work or I/O performance for reclaimed memory.

See `references/wsl2-memory-accounting.md` for the exact probes, accounting model, and non-destructive decision rules.

## Crash recovery (WSL2 restart)

When a previously-running autoresearch session dies because WSL2 itself stopped (not because the agent crashed), use `codex exec resume --last` to restart without losing session context. The procedure is:

1. **Diagnose:** `wsl -l -v` — if the distribution shows `Stopped`, that is the root cause. Start it with any `wsl bash -lc '...'` command.
2. **Revert interrupted edits:** The crash leaves the training file dirty from whatever experiment was mid-flight. `git checkout -- train.py` to reset to the incumbent commit (identified via `grep "keep" results.tsv | tail -1`).
3. **Verify sandbox:** Run the launcher's `test` mode. A WSL restart doesn't change config, but verify anyway.
4. **Resume non-interactively:** `codex exec --cd "$ROOT" --model "$MODEL" --dangerously-bypass-approvals-and-sandbox resume --last "<prompt>"`. The `--cd`, `--model`, and bypass flags are exec-level and MUST come before the `resume` subcommand — putting them after produces `error: unexpected argument '--cd'`.
5. **Verify the agent is alive:** Within 60 seconds, `pgrep -af "codex|bwrap"` should show the full process tree, and runtime DBs should show recent mtimes.

**Critical pitfall:** On WSL2 systems where Codex was installed via Windows npm, `which codex` resolves to `/mnt/c/Users/.../npm/codex` — a JS shim missing `@openai/codex-linux-x64`. The launcher must prepend `~/.local/npm/bin` to PATH so the WSL-native binary is found inside the Bubblewrap sandbox.

See `references/wsl2-crash-recovery.md` for the full diagnosis sequence, recovery procedure, and pitfalls.

## Interactive shell discipline

- Put the required directory-navigation command first whenever the user must leave or switch folders.
- Give one command block at a time when the user is actively operating a terminal.
- Never include the shell prompt (`user@host:dir$`) in a command block.
- Distinguish Python source, Bash commands, PowerShell commands, and editor actions explicitly.
- If the user pasted prompt text or code into the wrong shell, first recover the shell (`Ctrl+C` for continuation prompts), identify the current prompt, and resume from the last confirmed step. Do not restart the workflow or change the repair strategy midstream without evidence.
- Keep instructions brief, precise, and professional during live debugging; ask for the verification output before advancing when an edit is safety- or correctness-relevant.
- When the user asks for the “complete Markdown/TOML file,” do not keep reposting rendered prose. Produce a literal artifact, verify it, and provide one copy command plus the expected hash.
- Do not call a near-total domain rewrite “targeted.” Explain early which structural ideas remain and which task-specific content must be replaced.
- Do not repeatedly broaden sandbox permissions after version-specific device/profile failures. Report the exact enforcement trade-off and either use the last verified narrow configuration or recommend a stronger isolation boundary such as a dedicated distro/container.

## Pitfalls

- `python3` in the Windows/MSYS terminal is not the WSL Python; do not use host-terminal observations to claim WSL GPU readiness.
- Ubuntu's PEP 668 error means system `pip install` is blocked; project-local `uv sync`/`uv run` is the intended isolated path.
- An NVIDIA GPU being visible through `nvidia-smi` does not guarantee that every third-party CUDA kernel supports its compute capability.
- A reduced local configuration changes throughput and possibly the optimization regime; retain the exact configuration in experiment records.
- **A green consumer loop can hide a research island that was never built.** Before trusting bridge/batch automation receipts (`no_queue`, `0 candidates`), verify the research repo itself: it contains actual research code (not a stale clone of the parent repo — check `git log` and top-level layout), a queue or artifact producer exists, and results are being written. A watchdog PASS over an empty queue certifies nothing.

## References

- See `references/blackwell-wsl-autoresearch.md` for the concrete WSL2/RTX Blackwell kernel failure and verified fallback pattern from the initial bring-up.
- See `references/source-faithful-autoresearch.md` for upstream-contract verification, Codex CLI preflight, sandbox/CUDA evidence requirements, and the distinction between agent-driven autoresearch and hardcoded parameter sweeps.
- See `references/codex-wsl2-gpu-sandbox.md` for version-pinned `/dev/dxg` evidence, why a GPU-only probe is insufficient, the outer-Bubblewrap fallback, and containment-reporting caveats.
- See `references/wsl2-crash-recovery.md` for the full WSL2 crash recovery procedure: diagnosing WSL stops, reverting interrupted experiments, resuming sessions non-interactively, and the Windows-npm-shim PATH pitfall.
- Use `scripts/codex-wsl2-gpu-bwrap.sh` as a parameterized outer-boundary test/launch/resume template when the reference's preconditions apply. Supports `test`, `launch`, and `resume` modes.
