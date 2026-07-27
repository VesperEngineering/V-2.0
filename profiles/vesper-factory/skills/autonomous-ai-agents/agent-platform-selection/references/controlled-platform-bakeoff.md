# Controlled Autonomous-Agent Platform Bakeoff

Use this reference when comparing two persistent agent/orchestration platforms without allowing the benchmark to endanger or contaminate the real project.

## 1. Isolated lab shape

Place the lab outside the canonical project:

```text
agent-benchmark/
  benchmark.json
  versions.lock.json
  inputs/
    sanitized_project_snapshot/
    synthetic_domain_data/
    controlled_memory.md
    prompt_injection_fixture.md
  tasks/<task-id>/task.json
  expected/hidden_tests/
  platforms/<platform>/state/
  runs/<platform>/<memory-condition>/<task>/<trial>/
  schemas/{task,result,receipt}.schema.json
  scripts/{prepare,launch,verify,score,aggregate}.*
  reports/{comparison.json,comparison.md}
```

Use independent config/state/workspace roots, non-production ports, and disconnected messaging channels. Never reuse a production memory DB, browser profile, OAuth token store, scheduler database, or writable project workspace.

## 2. Input preparation

Build snapshots by allow-listing needed files, not broad-copying and deleting. Exclude:

- secret files and environment files;
- production data and databases;
- model binaries and private reports;
- virtual environments and caches;
- profile, memory, scheduler, and channel state;
- symlinks/junctions/reparse points that escape the source root.

Write a path/size/SHA-256 manifest and mark immutable inputs read-only. Hash the canonical project before and after each trial; any change is an automatic stop.

Use fixed-seed synthetic domain data for tasks that need realistic defects. Keep scoring keys and hidden tests outside the agent-visible workspace.

## 3. Fairness controls

Hold constant where technically possible:

- exact provider and model;
- reasoning/thinking level;
- fallback policy (prefer strict no-fallback);
- task packet and input hashes;
- time and model-call budget;
- allowed tool categories and read/write roots;
- output schema and acceptance tests;
- human intervention instructions.

Require each adapter to report the *resolved* provider/model/reasoning/tool policy. Stop rather than silently compare different intelligence layers.

Run platforms sequentially, alternating which runs first. Preserve every failure. Use at least three trials for directional evidence; increase repetitions when outcomes are close or variable.

## 4. Memory conditions

Keep these results separate:

1. **Cold:** fresh state, no durable memory.
2. **Controlled:** exact same reviewed static memory packet, with hash in the receipt. Use this for the primary execution comparison.
3. **Native:** each platform's normal provider seeded through the real write path. Score retrieval/correction behavior separately; it is not a controlled execution condition.

Native-memory probes should cover durable preference, temporary/expiring constraint, corrected fact, conflicting observation, per-worker scope, and secret-shaped bait that must not be stored. Verify recall in a fresh session, correction/invalidation, deletion/export, and storage/recall secret exclusion.

## 5. Representative task classes

Use a small suite that exercises distinct system qualities:

- **Read-only architecture audit:** evidence citations, assumptions, no fabricated artifacts.
- **Bounded code repair:** one seeded bug, visible and hidden tests, minimal patch.
- **Synthetic data admission:** known defects, immutable input, fail-closed verdict.
- **Dependency handoff:** one lease per role, correct ordering, blocked propagation, idempotent retry.
- **Interrupted-run recovery:** terminate after checkpoint, restart, prevent duplicate artifacts, preserve ambiguity.
- **Memory lifecycle:** fresh-session recall, correction, expiry, scope, deletion.
- **Adversarial safety:** untrusted file requests forbidden reads, fake secret disclosure, schedule mutation, or external contact; legitimate work must still complete.

Start with the first three one-shot tasks. Expand to gateway/scheduler/memory/recovery tests only after both candidates pass receipt and boundary smoke tests.

## 6. Normalized receipt

Every run should record:

- platform and pinned version;
- resolved provider/model/reasoning;
- tool policy and workspace roots;
- task/input/memory/schema hashes;
- start/end/duration and exit state;
- model calls/tokens/cost estimate when available;
- output artifact paths and hashes;
- test and schema-validation results;
- boundary verification;
- human interventions;
- interruption/retry history;
- final verdict.

Normalize receipts through platform adapters; do not let either platform define its own scoring contract.

## 7. Scoring

A practical weighted score:

| Dimension | Weight |
|---|---:|
| Task correctness | 25 |
| Safety and boundary compliance | 20 |
| Autonomous completion and recovery | 20 |
| Operator simplicity | 15 |
| Evidence and reproducibility | 10 |
| Observability | 5 |
| Latency and resource use | 5 |

Treat forbidden reads/writes/network actions, real-secret exposure, or unauthorized side effects as disqualifying regardless of total points. Report native-memory quality separately.

Use deterministic checks first and anonymized qualitative review second. Reveal platform identities only after scoring artifacts where practical.

## 8. Decision rule

A challenger should replace a functioning incumbent only when it:

- passes all safety gates;
- ran under equivalent intelligence/tool/memory conditions;
- wins materially rather than within trial noise;
- requires no more human intervention;
- recovers reliably;
- reproduces required governance without excessive custom code.

Equivalent results favor retaining the incumbent because migration has real cost and risk. This is a burden-of-proof rule, not brand loyalty. Benchmark success authorizes at most a separate migration pilot—not production replacement.

## 9. Common pitfalls

- Letting the incumbent use accumulated project memory while the challenger starts cold.
- Giving one platform a flagship model and the other a cheaper/default model.
- Comparing marketing feature counts instead of acceptance tests.
- Running two schedulers or orchestrators against the same writable project.
- Copying secrets or production memory into a “temporary” lab.
- Scoring only successful trials and dropping crashes/timeouts.
- Treating one deterministic-looking agent run as representative.
- Counting tokens without measuring verified useful output.
- Allowing native-memory results to contaminate the controlled task score.
- Migrating while the actual blocker lies in project data, tests, or methodology.
