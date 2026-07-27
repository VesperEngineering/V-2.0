# Restarting an autoresearch session after a WSL2 crash

Use this reference when a previously-running Codex autoresearch session died because WSL2 itself stopped (not because the agent crashed). The symptom is usually "my terminal sessions quit unexpectedly" — the root cause is that WSL2 was stopped or restarted, which kills every process inside it including bwrap, codex, and any training run.

## Diagnosis sequence

1. **Check WSL state first.** Run `wsl -l -v` from Windows. If the distribution shows `Stopped`, that is the root cause — not Codex, not the GPU, not the sandbox. Start it with any `wsl bash -lc '...'` command.
2. **Confirm the crash timestamp.** The Codex runtime writes to `~/.cache/<runtime-dir>/` — check file mtimes. The `history.jsonl` last entry timestamp tells you the exact moment the session died. Compare against WSL uptime (`uptime -p`).
3. **Check for an interrupted experiment.** The repo will have uncommitted edits to the training file (`train.py` or equivalent) if the crash happened mid-experiment. The `run.log` will be stale or incomplete. `results.tsv` shows the last completed experiment.
4. **Identify the incumbent.** `grep "keep" results.tsv | tail -1` gives the last kept experiment — this is the commit to reset to.

## Recovery procedure

### 1. Start WSL2 and verify GPU

```bash
wsl bash -lc 'nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv'
```

If WSL was stopped, any `wsl` command starts it. Confirm the GPU is visible and has free memory.

### 2. Revert the interrupted experiment's uncommitted edits

The crash leaves the training file in a dirty state from whatever experiment was running when WSL died. Revert to the incumbent before resuming:

```bash
cd ~/vesper-autoresearch   # or your research workspace
git status -s              # shows the dirty file(s)
git checkout -- train.py   # revert to incumbent HEAD
git status -s              # should show only untracked logs/cache
```

Do NOT commit the interrupted experiment — it was never evaluated. The `results.tsv` already records its outcome as `discard` or has no entry at all.

### 3. Run the sandbox self-test

```bash
~/run-vesper-codex.sh test   # or your launcher's test mode
```

Verify every boundary: workspace writable, outside read-only, Windows mounts masked, other clones masked, real codex home masked, GPU visible. A WSL restart does not change sandbox config, but verify anyway — the crash could have been caused by a config change the user made before the restart.

### 4. Resume the session non-interactively

The key command is `codex exec resume --last`. This resumes the most recent Codex session and continues it autonomously. **Flag order matters** (see pitfall below).

For a launcher that uses the outer-Bubblewrap pattern, add a `resume` mode:

```bash
run_resume() {
  install -m 600 "$HOME/.codex/auth.json" "$RUNTIME/auth.json"
  exec bwrap "${BWRAP_ARGS[@]}" \
    codex exec \
      --cd "$ROOT" \
      --model "$MODEL" \
      --dangerously-bypass-approvals-and-sandbox \
      resume --last \
      "<resume prompt: state the incumbent commit, last discarded experiment, and instruction to continue the loop without pausing>"
}
```

### 5. Verify the agent is alive

Within 30-60 seconds of launch, check:

- **Process tree:** `pgrep -af "codex|bwrap"` — should show bwrap → node codex → codex-linux-x64 native binary → codex-code-mode-host
- **Runtime activity:** `find ~/.cache/<runtime-dir>/ -type f -mmin -2` — DBs (goals, state, logs) should have recent mtimes
- **Repo activity:** the training file and run.log should show new mtimes within 2-3 minutes as the agent edits, commits, and runs the first experiment
- **Session rollout:** the resumed session's `.jsonl` rollout file grows as events flow

## Pitfalls

### `which codex` resolves to the Windows npm shim (CRITICAL)

On a WSL2 system where Codex was installed via Windows npm (`npm install -g @openai/codex`), `which codex` inside WSL resolves to `/mnt/c/Users/<user>/AppData/Roaming/npm/codex` — a JS shim that throws `Error: Missing optional dependency @openai/codex-linux-x64` because the Windows install doesn't include the Linux native binary.

The WSL-native install lives at `~/.local/npm/bin/codex` (or wherever `npm root -g` points inside WSL). The launcher MUST prepend this to PATH:

```bash
export PATH="$HOME/.local/npm/bin:$PATH"
```

Without this, `bwrap` will find the Windows shim, which will fail inside the sandbox because it cannot exec a Linux binary that isn't installed. This failure looks like a sandbox issue but is really a PATH resolution issue.

### `codex exec resume` flag order (CRITICAL)

`--cd`, `--model`, `--dangerously-bypass-approvals-and-sandbox` are `codex exec`-level flags. They must come BEFORE the `resume` subcommand:

```bash
# CORRECT
codex exec --cd "$ROOT" --model gpt-5.6-terra \
  --dangerously-bypass-approvals-and-sandbox \
  resume --last "<prompt>"

# WRONG — produces: error: unexpected argument '--cd' found
codex exec resume --last \
  --cd "$ROOT" --model gpt-5.6-terra \
  --dangerously-bypass-approvals-and-sandbox \
  "<prompt>"
```

The error message suggests `-- --cd` as a workaround, but that passes `--cd` as a prompt argument, not a flag. Do not follow the tip; reorder the flags.

### Do not restart with `launch` mode

`launch` starts a fresh interactive Codex session with `codex --cd ... --model ...` (no `exec`, no `resume`). This creates a new session and loses the context of the interrupted one — the agent won't know what experiments it already ran, what the incumbent is, or what it was about to try. Always use `exec resume --last` for crash recovery.

### The runtime cache survives WSL restarts

`~/.cache/<runtime-dir>/` (containing `auth.json`, session rollouts, history, DBs) persists on the WSL filesystem across WSL stops/starts. You do not need to re-authenticate or rebuild the runtime. Just verify `auth.json` is present and the session rollout file exists.

### The session rollout file path

Codex stores session rollouts at `~/.cache/<runtime-dir>/sessions/<YYYY>/<MM>/<DD>/rollout-<timestamp>-<session-uuid>.jsonl`. The `history.jsonl` file logs the last user action per session. Use `tail -1 history.jsonl` to find the most recent session ID and timestamp, then find the matching rollout file to inspect what the agent was doing when it died.

## When NOT to resume

- **Sandbox self-test fails:** Do not resume. The crash may have been caused by a config change that broke isolation. Fix the sandbox first.
- **Git tree is clean but HEAD doesn't match the recorded incumbent:** Someone (or a previous agent) committed something unexpected. Investigate before resuming.
- **`auth.json` is missing:** Codex can't authenticate. Do not proceed — the agent will loop on auth failures.
- **GPU is not visible after WSL restart:** WSL2 GPU passthrough can fail after a Windows update or driver change. Do not resume until `nvidia-smi` works inside WSL.
