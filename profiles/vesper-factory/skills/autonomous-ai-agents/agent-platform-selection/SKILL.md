---
name: agent-platform-selection
description: Objectively select or retain an autonomous-agent platform by separating orchestration needs from model/coding quality, scoring operational fit, and accounting for migration cost and the project's actual bottleneck.
version: 1.1.0
created_by: agent
---

# Agent Platform Selection

## Use when

Use when a user asks which autonomous-agent framework, personal assistant, coding agent, or multi-agent control plane is best for their situation—for example Hermes, OpenClaw, OpenHands, Codex, Claude Code, OpenCode, or a workflow engine.

The goal is not to crown a universal winner. It is to identify the smallest system that satisfies the user's actual operating contract.

## Core distinction: intelligence versus orchestration

Always separate these layers before comparing products:

1. **Intelligence/execution layer** — the model or coding worker that reasons, edits, tests, and researches (for example Codex, Claude Code, OpenCode, or an OpenHands agent).
2. **Orchestration layer** — persistence, schedules, events, memory, messaging, worker identities, queues, dependencies, receipts, and human gates.
3. **Project/domain layer** — the data, tests, evaluation contract, artifacts, and business/scientific bottlenecks that determine whether the work is actually valid.

A strong coding agent is not automatically a durable autonomous operating system. A rich personal assistant is not automatically the best governed research queue. A framework migration cannot repair invalid data or evaluation methodology.

## Broad ecosystem, narrow active context

Do not confuse the size of the installed ecosystem with the size of each model turn. A capable platform can keep many plugins, MCP servers, skills, and tools discoverable while exposing only a task-specific allowlist to each worker. The inference risk comes from injecting excessive tool schemas and irrelevant instructions—not from capabilities that remain unloaded.

Evaluate both levels:

- **Platform toolbox:** Can missing capabilities be added, audited, version-pinned, and maintained?
- **Worker toolbelt:** Can each role/job receive only the tools, read/write roots, and authority it needs?

A broad ecosystem is a real advantage only when selection is lazy, permissions are narrow, and supply-chain/tool-schema overhead is visible. Prefer central breadth plus per-worker restraint over either a globally limited platform or an “everything on every turn” configuration.

## Evidence-first comparison procedure

### 1. Freeze the user's operating contract

Extract the requirements before naming a winner:

- operating system and local/cloud constraints;
- always-on versus interactive use;
- required messaging channels and voice/device support;
- scheduled and event-driven work;
- single agent versus isolated specialist workers;
- durable queue, dependencies, retries, receipts, and observability;
- persistent memory and reusable skills;
- model/provider freedom and subscription/OAuth compatibility;
- sandboxing, secret handling, and human-gated authority;
- Git-centered versus intentionally local/non-Git workflow;
- tolerance for Docker, servers, Node/Python runtimes, and maintenance;
- migration cost and acceptable downtime.

Weight these criteria from the user's stated priorities. Do not use a generic feature count.

### 2. Classify candidates by product category

Compare like with like:

- **Personal-assistant platforms** emphasize channels, devices, voice, local gateways, and broad life automation.
- **Agent orchestrators** emphasize durable schedules, profiles/workers, queues, memory, tools, and messaging.
- **Engineering control centers** emphasize repositories, sandboxes, issue/PR workflows, remote agent backends, and team automation.
- **Coding agents** emphasize code reasoning and implementation quality but may need an external scheduler, queue, gateway, and memory layer.
- **Deterministic workflow tools** emphasize explicit integrations and repeatability but are not substitutes for open-ended reasoning.

A product may span categories; score only documented, operational behavior.

### 3. Use current primary sources

For each shortlisted platform, collect from official documentation, repository README, release metadata, and security/architecture pages:

- supported OS/runtime and installation burden;
- scheduler/event semantics;
- worker/session isolation and durable coordination;
- provider authentication, including subscription OAuth versus metered API keys;
- messaging/device surfaces;
- sandbox and host-access defaults;
- observability and receipt/log model;
- release recency, licensing, and project status.

Repository stars, social popularity, and issue counts are context—not proof of fit, stability, security, or feature quality. State the observation date because these systems change quickly.

When managed web search is unavailable, use official raw README URLs and public repository APIs rather than stopping at search snippets.

### 4. Inspect the incumbent before recommending migration

If a system is already operating, verify what is working now:

- natural scheduled runs;
- durable worker handoffs;
- current queue/task state;
- message delivery;
- restart behavior;
- evidence and monitoring surfaces;
- known reliability incidents and their mitigations.

Count the infrastructure a migration would have to recreate. Existing investment is not a reason to keep a bad tool, but replacing verified capabilities has real cost and risk.

### 5. Identify the actual limiting factor

Ask what currently prevents a useful result. Typical bottlenecks include:

- invalid or stale data;
- weak evaluation methodology;
- missing artifacts or tests;
- unclear human authority;
- scheduler unreliability;
- inadequate worker quality;
- poor observability.

If the bottleneck is in the domain/project layer, changing agent frameworks is usually displacement activity. Recommend fixing the bottleneck unless the current platform itself materially causes it.

### 6. Produce one recommendation and explicit switch conditions

Lead with a single answer. Then provide:

- why it wins the weighted criteria;
- where competing tools genuinely win;
- the incumbent's real weaknesses;
- migration cost and what must be rebuilt;
- measurable conditions that would justify switching later.

Do not hedge into “use everything.” A hybrid is justified only when each layer has a distinct owner—for example one orchestrator using a separate coding agent as its worker.

## Decision patterns

These are category heuristics, not permanent product rankings:

- Choose a **personal-assistant platform** when broad channels, voice, phones, device nodes, and whole-life automation dominate.
- Choose an **engineering control center** when GitHub/issue/PR automation, containers, remote agent backends, and software-team workflows dominate.
- Choose a **coding agent alone** when the user mainly wants interactive implementation and does not require durable scheduling, messaging, memory, or multi-worker queues.
- Choose an **agent orchestrator** when the user needs a persistent, scheduled, multi-role local operation with durable state and human gates.
- Keep the incumbent when it already satisfies the operating contract and the current blocker lies in the project/data/evaluation layer.

## Platform-freeze recommendation

When migration has no evidence-backed benefit, recommend a bounded platform freeze rather than indefinite loyalty:

1. Freeze the orchestration choice for a defined period, commonly 30 days.
2. Measure natural-run reliability, completed useful tasks, blocker rate, evidence quality, human interruptions, and turnaround time.
3. Keep a small portability inventory: project files, worker role contracts, schedules, queue schema, evidence paths, and provider/auth assumptions.
4. Re-evaluate only against measured failures and explicit switch thresholds.
5. Never run two full orchestrators against the same writable project merely for comparison; use a read-only or isolated bakeoff.

## Retain-and-improve path

When the user chooses the incumbent but wants the best available system, convert the comparison's weaknesses into a bounded capability-gap program instead of continuing platform shopping.

1. Maintain one durable gap register with: evidence, impact, smallest correction, acceptance test, authority class, status, and dependency.
2. Separate **platform gaps** (isolation, least-privilege tools, scheduling/idempotency, observability, memory/knowledge portability, recovery) from **project bottlenecks** (data validity, tests, evaluation design). Work both, but do not imply a platform feature fixes a domain defect.
3. Close cheap evidence gaps first. Verify the project interpreter/environment before installing dependencies; verify a claimed missing capability against live configuration before adding a plugin.
4. Group related gaps into a lean dependency graph rather than one card per suggestion: authority/isolation/security audit → deterministic lifecycle contract → shared knowledge/portability contract → minimum implementations → independent review.
5. Give every implementation a fail-closed acceptance gate and a read/write scope. Keep high-impact authority—credentials, spending, broker/execution, risk, deployment, promotion, and schedules—separately human-gated.
6. Preserve the user's chosen version-control posture. If Git is deliberately deferred, use before/after SHA-256 manifests and backups without pretending they equal full history or atomic rollback.
7. Do not install the rejected competitor “just to have it.” Keep an isolated bakeoff plan dormant until measured switch conditions are met.
8. Report progress as: gap closed with evidence, gap partially mitigated, or open gate. Avoid claiming that an audit or design contract is an implemented control.

This path reconciles ecosystem breadth with simplicity: expand the incumbent only where a documented gap and measurable acceptance test justify the capability.

## Controlled platform bakeoff

When the user wants evidence rather than a recommendation, build the comparison outside the canonical project. Pin platform versions, isolate state/config/channels, sanitize inputs by allow-list, use synthetic data, and verify canonical project hashes before and after every run. Start with one-shot tasks; test gateways, schedulers, and native memory only after both candidates pass the basic safety boundary.

Hold constant the model, reasoning level, task packet, controlled-memory hash, time/model-call budget, and allowed tool categories where technically possible. Run platforms sequentially and alternate order to avoid account-quota contention. Use repeated trials because agent outputs are nondeterministic. Score hidden acceptance tests, safety, recovery, evidence, operator interventions, observability, and resource use; treat a forbidden read/write/network action as disqualifying regardless of aggregate score.

For a complete lab layout, memory conditions, representative task suite, scoring rubric, and decision gates, see `references/controlled-platform-bakeoff.md`.

## Bias controls

- If the active assistant belongs to one candidate platform, explicitly acknowledge that conflict and still name where competitors are stronger.
- Do not equate “already installed” with “best,” but do count verified behavior and migration cost.
- Do not equate model quality with orchestration quality.
- Do not recommend a migration because it feels productive.
- Do not make unsupported negative claims about a competitor; say “not evidenced in the reviewed sources” when appropriate.
- Do not hide operational weaknesses of the recommended platform.

## Output format

Use this concise structure:

1. **Straight verdict** — one platform or architecture.
2. **Counterfactual** — what you would choose from zero with the current project state.
3. **Weighted comparison** — short table with best use, fit, and tradeoff.
4. **Actual bottleneck** — why platform choice does or does not affect it.
5. **Single next action** — retain, migrate, or run an isolated bakeoff.
6. **Switch conditions** — objective evidence that would reverse the recommendation.
7. **Primary sources** — official links and observation date.

For a reusable scoring worksheet and source checklist, see `references/platform-evaluation-checklist.md`.

## Pitfalls

- Ranking by stars or marketing breadth.
- Comparing a coding CLI directly with a persistent assistant without separating layers.
- Recommending a second orchestrator that duplicates schedules or writes to the same project.
- Ignoring subscription/OAuth economics and silently assuming metered API access.
- Treating more autonomous activity as better than bounded, evidence-producing work.
- Migrating while the real blocker is invalid data, evaluation leakage, or missing scientific controls.
- Giving a “no favorites” answer that conceals the recommended platform's weaknesses.
