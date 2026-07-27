# Milestone C recurring research schedule preflight (2026-07-21)

## Proven predecessor

Milestone B established the no-agent scheduler proof pattern:

- natural one-shot job `0d283c352732`;
- execution `a8f07e767b154ef999f74259af191570` completed exactly once;
- active duplicate count 0 and job auto-removed;
- final receipt SHA-256 `5c5a7cf3597b89bdcc678b21c6af30d98129a88573683be7d2690ac6a3d3611e`;
- natural receipt SHA-256 `6a5f5ec928c9a990389cfdc70ba6f8ff2b4435e37e1de13d9f2e51be73bb1751`;
- machine wrapper SHA-256 `b4f9724d2de1e40818d349630deb4241e4ce1006b565157eb0a593791d511557`.

The historical Milestone B agent supervisor remained paused. This proves one finite natural firing, not a recurring Milestone C supervisor.

## Current exact conflict

Enabled job `aaade396f41e` (`Research Batch Advance`) already runs `vesper_research_batch.py` at `*/30 * * * *`. It window-gates, refreshes `D:/vesper-research/experiment_queue.json`, leases one PENDING item, runs it, and marks it terminal. It does not require a Milestone C Kanban/receipt gate. Its timestamp-only `RunLock` may break stale ownership while a crashed queue row remains `RUNNING`, so it is not restart/no-duplicate proof.

At audit time the queue contained one COMPLETE smoke item and no PENDING item; the job was no-op but remained an exact future executor conflict. A replacement must not coexist with it. Pause/read back `aaade396f41e` only after the supervised Milestone C gate passes, then arm the new job. Keep the old ID for rollback.

Adjacent jobs were:

- `90cf5b3b9d69` — Kanban research-direction sync, every 30 minutes;
- `7cfcf841173c` — research artifact to Kanban bridge, every 15 minutes;
- `2763a0f176df` — weekly LLM research engineer.

They are not exact executors but can inject queue items or review cards, so artifact/key namespaces must be isolated or explicitly reconciled.

## Target recurring tick contract

Recommended shape after a supervised experiment and independent review pass:

```text
name: Vesper Milestone C Research Supervisor
cadence: */30 * * * *
mode: no-agent
wrapper: ~/.hermes/scripts/vesper_milestone_c_research_once.py
workdir: stable reviewed Milestone C worktree
rollback: hermes cron pause <new-job-id>
```

Each tick:

1. Verify exact activation-card/root identities and bound supervised/review receipt hashes.
2. Verify reviewed worktree HEAD and tracked cleanliness.
3. Acquire a generation-bound singleton owner; also detect the legacy research lock.
4. Read Kanban in `mode=ro` and require no active run for the canonical Milestone C IDs/key prefix.
5. Require no lifecycle row in DISPATCHED/RUNNING/CANDIDATE_READY/EVALUATING and no queue item RUNNING.
6. Select at most one dependency-ready PENDING item.
7. Derive identity from objective + data-manifest + evaluator + candidate-spec hashes and reserve it transactionally.
8. Execute fixed argv once under hard deadline and zero retry.
9. Atomically publish candidate/evaluation/decision/receipt/append-only ledger state.
10. Add a receipt-hash-aware Kanban update through fixed CLI only.

Recovery rule:

- validated terminal receipt and supporting hashes match: reconcile/replay metadata only;
- stale/partial/missing/conflicting evidence: HELD and alert; do not reset, recover by rerunning, or create a successor automatically.

Normal outside-window/no-work ticks produce explicit IDLE/no-op posture, not productive PASS.

## Install-time dedup

Hermes cron create has no idempotency key. Under an installer lock, scan enabled and paused definitions by exact name, script, schedule, workdir, mode, source SHA, wrapper SHA, and contract hash. Reuse exactly one equal row; create only from zero; HOLD on more than one or on a mismatched same-name row. After creation, persist job ID + canonical definition hash, run one natural/probe verification as allowed, and re-read state/runs/receipt before claiming activation.