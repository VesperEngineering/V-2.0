# Guarded WSL GPU Evaluation and Crash Recovery

Use this pattern when retrying a CUDA-backed Model Lab evaluator after a timeout, stale state, or unexpected Windows reboot.

## Distinguish a live run from stale state

Treat `current.json` as a display receipt, not process authority.

1. Read `runs/state/current.json` and the matching report/evaluation artifacts.
2. Check both Windows and WSL for the exact evaluator/trainer command line.
3. If state says `EVALUATING` or `RUNNING` but no matching process exists, classify it as stale/interrupted.
4. Search the run artifacts for a traceback or explicit failure receipt. A Python exception handled by the evaluator should write `FAILED`; an abrupt OS reboot can leave the last `EVALUATING` write untouched.
5. Inspect Windows Event Log for the reboot and check Windows CrashDumps/Minidump/LiveKernelReports plus WSL core-dump locations. Kernel-Power Event 41 with `BugcheckCode=0` proves an unclean reboot, not a specific software cause, and commonly has no dump.
6. Do not report the stale dashboard text as real progress and do not overwrite evidence merely to make the UI look correct.

## Single-process guarded retry

Never respond to a long evaluator by launching another copy. One evaluator can be slow because deterministic generation runs every benchmark item through both base and adapter models.

Preflight:

- Confirm the frozen training report and benchmark manifest exist.
- Reject launch if `pgrep` finds an evaluator or trainer already running.
- Verify `torch.cuda.is_available()`, device identity, BF16 support if required, and current `nvidia-smi` memory.
- Check host RAM against the user's total-RAM ceiling.

Use two complementary GPU limits:

1. **Preventive per-process allocator limit:** before loading the model, call `torch.cuda.set_per_process_memory_fraction(...)`. Set this below the user's total-GPU ceiling so the process cannot consume the whole allowance.
2. **Host-level total-VRAM watchdog:** sample `nvidia-smi --query-gpu=memory.used` from Windows and stop the evaluator if total device usage reaches the user's ceiling. Monitor host RAM in the same loop.

Leave material headroom between the allocator cap and total-device cap. The allocator limit applies only to that PyTorch process; unrelated GPU consumers count only in total `nvidia-smi` usage. A watchdog is reactive, so headroom is what prevents a brief external allocation from crossing the total ceiling between samples.

Example policy for a 16 GiB consumer GPU and a user-declared 14 GiB total cap:

- PyTorch evaluator allocator: 12 GiB maximum.
- Total GPU guard: stop at 14,336 MiB.
- Host RAM guard: stop at the user's declared percentage.
- Telemetry cadence: 0.5–2 seconds, with compact human-facing output every 30 seconds.

Run the evaluator unbuffered and capture combined stdout/stderr. On a guard violation:

1. send `TERM` only to the exact evaluator command/run ID;
2. wait briefly;
3. terminate the WSL distro only if the child does not exit and no unrelated WSL workload is authorized;
4. record the guard reason and non-success exit.

## Waiting without duplicate launches

Launch the guard once as a tracked background process. If the orchestration tool clamps a requested wait duration, continue waiting on that same PID/session or use one blocking host-side `psutil.Process(pid).wait(...)`. A wait timeout is not evaluator failure and never authorizes a second launch.

## Completion verification

Before reporting success:

1. require evaluator exit code zero and no guard reason;
2. parse the exact evaluation receipt;
3. verify run ID, `COMPLETE` status, benchmark manifest SHA-256, and expected base/adapter detail counts;
4. read `current.json` and require `COMPLETE` with the matching run ID;
5. run the Windows console `--smoke-test` and confirm it renders the receipt-backed completed state;
6. report peak total VRAM and peak host RAM from the guard log;
7. remove the temporary guard script, preserve the durable evaluation receipt, and restore WSL to its prior stopped state when no workload remains.

A completed comparison can still be negative evidence. Zero schema-valid or zero-pass results mean the pipeline ran; they do not justify more steps, promotion, or repeated tuning against the same benchmark. Improve independently reviewed task-diverse data or evaluation design before spending another GPU run.
