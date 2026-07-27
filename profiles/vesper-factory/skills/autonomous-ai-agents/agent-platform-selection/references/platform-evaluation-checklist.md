# Autonomous Agent Platform Evaluation Checklist

Use this worksheet for a dated comparison. Fill it from primary sources and current runtime evidence; do not score from memory.

## 1. User operating contract

| Criterion | Weight 1–5 | Required behavior | Evidence/source |
|---|---:|---|---|
| Always-on durability | | Service/daemon, restart behavior, missed-run handling | |
| Scheduled/event work | | Cron, webhooks, event triggers, retries | |
| Multi-worker coordination | | Isolation, queue, dependencies, concurrency bounds | |
| Messaging/device access | | Required channels, voice, mobile/device nodes | |
| Persistent context | | Memory, sessions, skills/procedures | |
| Provider economics | | Subscription OAuth, API keys, fallback behavior | |
| Local/cloud boundary | | OS support, sandbox, filesystem scope | |
| Observability | | Current status, history, receipts, stale/error posture | |
| Human authority gates | | Spend, secrets, deployment, execution, promotion | |
| Setup/maintenance burden | | Runtimes, Docker, services, upgrades | |
| Project workflow fit | | Git-centered or local/non-Git, data/research needs | |
| Migration cost | | Schedules, roles, memory, dashboards, evidence to recreate | |

## 2. Candidate source packet

For each candidate record:

- Official homepage/docs:
- Official repository:
- Documentation/release observation date:
- Latest release and date:
- License:
- Supported OS/runtime:
- Service/daemon model:
- Scheduling and event mechanisms:
- Multi-agent/session/queue semantics:
- Model providers and subscription OAuth:
- Messaging/device surfaces:
- Sandbox and host-access defaults:
- Monitoring, receipts, and failure posture:
- Known limitations explicitly stated by the project:

Popularity metrics may be recorded separately but receive zero fit weight unless they produce a specific maintained integration or support advantage.

## 3. Incumbent evidence

If replacing an existing platform, inspect live state:

- Last natural scheduled runs and failures
- Current durable queue and dependencies
- Active worker/session continuity
- Message delivery and restart behavior
- Memory/skill assets that need export
- Operator dashboards and receipts
- Reliability incidents and mitigations
- Writable project roots and duplicate-dispatch risks

## 4. Layer ownership

Write one owner per layer:

| Layer | Owner |
|---|---|
| Orchestration/control plane | |
| Coding/reasoning worker | |
| Scheduler/event source | |
| Queue/dependency store | |
| Memory/skills | |
| Messaging gateway | |
| Project/domain evidence | |
| Human approval boundary | |

If two products own the same scheduler, queue, or writable project lifecycle, redesign before deployment.

## 5. Bottleneck test

Complete this sentence before recommending migration:

> The current useful-result bottleneck is ________, evidenced by ________. Changing platforms would address it by ________.

If the last blank is speculative or empty, retain the incumbent and repair the actual bottleneck.

## 6. Recommendation contract

- Straight verdict:
- Counterfactual from zero:
- Why the winner fits:
- Where the runner-up wins:
- Winner's real weaknesses:
- Migration work required:
- Single next action:
- Freeze/bakeoff duration:
- Switch thresholds:
  - scheduler reliability below ___;
  - task completion/evidence rate below ___;
  - human interruptions above ___;
  - required capability absent after ___;
  - maintenance time above ___.

## 7. Safe bakeoff rules

- Use read-only tasks or isolated project copies.
- Never let two orchestrators mutate the same queue, schedules, or working tree.
- Give candidates the same model, prompt, task, tool authority, and time/compute budget when comparing agent quality.
- Separate model performance from orchestration performance.
- Preserve exact logs, artifacts, elapsed time, interventions, and failure reasons.
- Choose from measured outcomes, not presentation polish.
