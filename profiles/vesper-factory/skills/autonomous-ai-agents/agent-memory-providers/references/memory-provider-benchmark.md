# Fair native memory-provider benchmark

Use this when comparing long-term memory systems for the same agent deployment. The result proves fitness only for the declared workload—not universal superiority.

## Isolation

- Keep production memory untouched.
- Put each candidate in its own disposable Hermes profile and provider store/vault.
- Pin the same model, reasoning level, toolsets, system instructions, task corpus, and sampling settings.
- Never copy production databases, transcripts, secrets, credentials, or benchmark answers into retrieval memory.

### Profile and store isolation traps

- Do **not** use `hermes profile create --clone-all` from a profile with real memory and assume the result is clean. Full cloning can copy the provider database and other durable state. Prefer a config-only clone, install/copy only the provider integration needed for the disposable profile, and verify provider statistics are exactly zero before seeding.
- Treat a zero-count check as a hard gate. If a supposedly fresh Mnemosyne profile reports existing working/episodic items, delete that disposable profile and recreate it rather than trying to distinguish copied production rows later.
- Some provider initialization commands persist a global/default vault path even when a disposable `--vault` argument or process-level vault override is supplied. Capture the original provider config first, initialize the disposable vault, restore the original path immediately, and verify the production profile still resolves its real vault. Never expose or copy credential/installation-secret fields while doing this.
- Bind every benchmark agent/CLI process to the disposable store explicitly. Do not rely only on whichever global config happens to be current.

### Evaluation-write contamination

Fresh sessions do not automatically mean fresh memory. Provider hooks may capture the benchmark prompt, retrieval output, and model answer after each trial. Those answers can then make later trials look successful.

Use this sequence:

1. Seed through the native provider path.
2. Remove or disable seed-session conversation captures while preserving the intended corpus. Prefer the provider's delete/forget API; direct database edits are acceptable only for a disposable store when the provider has no non-recursive cleanup path, and must be verified afterward.
3. Quiesce the store before freezing it (for SQLite/WAL providers, checkpoint and close all processes).
4. Freeze a hashed seed snapshot.
5. Before **every** evaluation call, restore the provider store from that snapshot.
6. Snapshot and restore the **no-memory baseline** too. “Built-in only” profiles can still retain session/conversation captures across retries, so a rerun may reveal an expected marker even without an external provider.
7. For correction and deletion phases, create separate hashed post-correction and post-deletion snapshots and restore the relevant one before every trial.
8. Make the runner restart-safe: append each raw call to JSONL immediately, restore the phase snapshot before every maintenance action, and never infer completion merely because an earlier partial run reached that action.

This prevents benchmark answers, provenance queries, prior trials, and failed-run retries from becoming retrieval evidence.

## Three conditions

1. **Cold start:** no durable memory. Measures the model/task baseline.
2. **Controlled packet:** seed both through their native write path with the same reviewed, redacted packet and record its raw SHA-256. This is the primary retrieval comparison.
3. **Native learning:** allow each provider's normal capture, consolidation, correction, expiry, and retrieval workflow. This measures deployment quality and maintenance cost.

Do not score a learning system before it crosses its own promotion threshold. An Open Second Brain vault with zero confirmed preferences is healthy but untrained; provide equal feedback opportunities and run `dream` before judging learned-preference quality. Conversely, `brain_feedback(force_confirmed=true)` is a legitimate explicit approved-write path for the **controlled packet** condition, but it bypasses normal three-signal learning and must never be reported as evidence about native preference induction.

## Corpus

Predeclare synthetic, non-sensitive items covering:

- stable facts and style/workflow preferences;
- project-scoped facts that must not leak;
- paraphrased retrieval;
- corrections and temporal ordering;
- contradictions requiring provenance-aware resolution;
- expiring/stale facts and irrelevant distractors;
- deletion/export probes;
- secret-shaped decoys that must be excluded;
- multi-session continuation and continuity after context compaction.

## Trials and scoring

- Use paired prompts in fresh sessions and randomize provider/task labels.
- Use fixed seeds when available; otherwise run at least five repeated trials per item. A two-trial run is a smoke test, not definitive evidence.
- Blind task-quality grading where practical.
- Include retrieval-disabled ablations for each provider.
- Separate exact recall from downstream tasks where memory must improve an artifact.
- Keep expected synthetic answer markers out of evaluation prompts. If the no-memory baseline guesses an expected marker—for example, a project name makes a file suffix obvious—mark that item non-discriminative rather than crediting provider memory.
- Score safety tasks separately from memory-benefit tasks. A no-memory baseline correctly answering an ordinary question or avoiding a scoped rule is expected; those items test contamination/leakage, not memory lift.
- Predeclare provenance as at least two dimensions: **traceability** (a provider returns a real evidence handle/artifact) and **exact metadata preservation** (it returns the original source label). Do not fail a traceable provider merely because its native evidence handle differs from another provider's source-field representation. Any post-hoc rubric correction must be reported alongside the original score.
- Report lifecycle phases independently: initial recall, correction/new-not-old, retirement/deletion, and post-deletion abstention. Do not issue a final provider verdict or claim cleanup complete while later lifecycle phases remain unexecuted.
Record:

- precision, recall, exact match/F1;
- stale-fact acceptance and correct stale rejection;
- correction/invalidation and contradiction resolution;
- temporal ordering and cross-project leakage;
- continuity after compaction and across fresh sessions;
- provenance, deletion, export, and auditability;
- downstream task completion quality;
- false-positive or irrelevant context injection;
- write/retrieval/consolidation latency;
- added prompt tokens, storage growth, failures, and operator maintenance.

Secret-decoy retention or scope leakage is a safety defect, not a minor accuracy miss. A provider that recalls more while injecting stale or cross-scoped facts is not better.

## Reproducibility manifest

Bind the verdict to provider/plugin versions, exact configuration, model, prompts, corpus hash, seed/trial IDs, evaluator, scoring rubric, and raw outputs. Report paired confidence intervals where useful. Report failures and overhead, not only wins.

## Decision and cleanup

1. Run cold and controlled synthetic conditions first.
2. Continue to a bounded live trial only if both pass safety/correction gates.
3. Review native-learning artifacts manually before declaring a winner.
4. Prefer the smallest system that materially reduces user corrections without increasing leakage, stale context, token cost, or maintenance.
5. Preserve the incumbent until the candidate wins and a separate migration plan is approved.
6. Export and hash benchmark artifacts, remove test memories through each provider's normal forget path, verify fresh-session non-retrieval, and delete only disposable stores created for the benchmark.
7. After cleanup, verify that disposable profiles and temporary roots are absent, the production provider's global/default path still points to its real store, and a production read-only export contains no active synthetic preference.
