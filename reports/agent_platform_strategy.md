# VESPER 2.0 Agent Platform Strategy and Capability Register

**Recorded:** 2026-07-23 17:21 EDT  
**Scope:** Consolidated recommendations from the Hermes/OpenClaw/autonomous-worker discussion.  
**Decision owner:** Brennan  
**Current recommendation:** Retain Hermes as V20's orchestrator and OpenAI Codex as the primary worker intelligence while running a controlled, isolated comparison against OpenClaw.

---

## 1. Executive recommendation

For V20's current requirements, keep this architecture unless an evidence-backed benchmark shows a better replacement:

```text
Telegram / V20 Dashboard
            |
            v
     Hermes orchestration
            |
            v
 Profiles + Kanban + Cron
            |
            v
 OpenAI Codex / other selected models
            |
            v
       Local V20 folder
```

This is a fit decision, not platform loyalty. V20 needs an always-on Windows agent, messaging, scheduled work, persistent memory, role isolation, a durable dependency queue, model/provider selection, evidence receipts, and human-gated authority. Hermes presently combines these requirements with less V20-specific adaptation than the alternatives.

The limiting factor in V20 is currently research validity—not the agent platform. Price-adjustment provenance, point-in-time universe construction, leakage-safe chronology, purging/embargo, untouched holdout discipline, and backtest accounting must be solved before another orchestrator can improve outcomes.

---

## 2. Key design principle: broad toolbox, narrow toolbelt

A robust ecosystem and accurate workers are compatible:

- **Platform level:** keep many capabilities installed and discoverable.
- **Worker level:** expose only the tools required for the assigned task.
- **Task level:** load only the relevant skills and evidence.

The number of installed tools is not the main inference risk. The risk comes from injecting too many tool schemas and irrelevant instructions into every model turn. That consumes context, increases routing ambiguity, and can reduce correct tool selection.

Recommended tool exposure:

| Worker | Normal active capabilities |
|---|---|
| Quant Research | Read-only project files, approved research sources, reports, Kanban |
| Data Engineer | Files, SQLite inspection, focused tests, Kanban |
| Development | CodeGraph, files, terminal, tests, Kanban |
| ML Systems | Frozen experiment contract, terminal, local CPU, artifact writing |
| Risk Review | Read-only files, receipts, test output, Kanban |
| Main orchestrator | Broad ecosystem, scheduling, messaging, browser, memory, worker coordination |

---

## 3. Platform comparison

### Hermes

**Best fit:** Hybrid personal/project orchestrator for V20.

**Relevant strengths**

- Independent profiles with separate instructions, models, and sessions.
- Durable Kanban cards, dependencies, comments, and worker logs.
- Built-in cron, messaging Gateway, Telegram delivery, and webhooks.
- OpenAI Codex/ChatGPT subscription authentication.
- Skills, plugins, MCP, custom tools, remote execution, and multiple providers.
- Persistent-memory provider support; V20 currently uses Mnemosyne.
- Native Windows operation and background desktop control.

**Observed weaknesses**

- Windows Gateway/TUI continuity has required diagnosis and recovery controls.
- Configuration breadth can become complex without disciplined profiles and tool allowlists.
- The multi-worker operator view required a custom V20 Live Team window.
- Shared local-folder workers are not hard-isolated by default.
- Agentic controller/steward decisions are not equivalent to a deterministic workflow engine.

### OpenClaw

**Best fit:** Broad, always-on personal assistant spanning channels, devices, and companion applications.

**Relevant strengths**

- Large public skills/plugin ecosystem.
- Multi-agent routing with separate workspaces, state directories, auth profiles, and SQLite session stores.
- Built-in scheduled tasks, command/script payloads, per-job tool policy, model and thinking overrides.
- Native Windows Hub plus Windows/WSL Gateway choices.
- Mobile/device nodes, voice/talk modes, Canvas, screen/camera/notification integration.
- Docker, SSH, and OpenShell sandbox backends.
- Multiple memory backends, including built-in SQLite/hybrid search, QMD, Honcho, LanceDB, and Memory Wiki.
- OpenAI Codex subscription support.

**Relevant limitations for V20**

- A workspace is only a default working directory, not a security boundary, unless sandboxing is enabled.
- Sandboxing is off by default.
- V20's durable dependency-aware Kanban, worker contracts, evidence gates, and dashboard would need to be reproduced or adapted.
- Running a second live orchestrator beside Hermes would create duplicate schedules, conflicting writes, memory contamination, and unclear authority.
- Broad ecosystem size does not prove better V20 task completion.

### OpenHands Agent Canvas

**Best fit:** Self-hosted, Git-centered software-engineering teams and automations.

**Strengths**

- Runs OpenHands, Codex, Claude Code, Gemini, or other ACP-compatible agents.
- Local, Docker, VM, remote, or cloud backends.
- Scheduled and webhook-driven automations.
- Strong engineering control-center and container story.

**Why it is not the current V20 default**

- Adds Agent Canvas, Agent Server, and optional Automation Server infrastructure.
- Most natural workflow centers on repositories, issues, and engineering automation.
- V20 is intentionally a lean, local, currently non-Git quant-research folder.

### OpenAI Codex

**Best fit:** Individual coding and codebase work.

Codex is an intelligence/implementation worker, not a complete replacement for V20's Gateway, scheduling, memory, worker roles, durable dependency queue, and operator visibility. Continue using it inside an orchestrator rather than treating it as the entire operating system.

### OpenCode

**Best fit:** Provider-neutral interactive coding with plan/build agents.

It is a credible coding-agent alternative but does not replace the complete autonomous project operating layer required by V20.

---

## 4. Persistent-memory recommendation

If every platform receives equally capable persistent memory, memory should be removed from the primary task-quality comparison. Equal memory narrows the platform gap but does not equalize workflow, safety, scheduling, observability, or isolation.

A fair memory design must distinguish:

1. Global user preferences.
2. Platform-specific operational facts.
3. Worker-specific role knowledge.
4. V20 project knowledge.
5. Task/experiment state.
6. Artifact and evidence indexes.

Memory must support:

- provenance and source;
- confidence/veracity;
- correction and invalidation;
- expiry;
- deletion/export;
- secret exclusion;
- per-worker and shared scopes;
- contradiction handling;
- stale-memory detection.

Persistence alone is insufficient. A system can store everything and still retrieve the wrong item, preserve a stale decision, or leak one worker's context into another.

For platform benchmarking, use three distinct memory conditions:

- **Cold start:** no durable memory.
- **Controlled memory:** identical, static, redacted memory packet supplied to both platforms.
- **Native memory:** each platform's best normal memory implementation; score this separately because the conditions are intentionally unequal.

Do not export credentials, tokens, raw `.env` files, raw transcripts, or unreviewed inferred conclusions into either benchmark memory store.

---

## 5. Current capability gaps and recommended corrections

### G1 — Worker isolation

**Gap:** V20 workers share the canonical local folder. One-worker-per-role reduces but does not eliminate conflicting writes.

**Recommendation:** Use task-owned disposable workspaces or snapshots for independent experiments. Keep canonical data read-only. Merge only reviewed artifacts through an explicit handoff.

**Priority:** High.  
**Status:** Not implemented.

### G2 — Versioning and rollback

**Gap:** V20 is intentionally not using Git yet. Hash manifests and backups are useful but objectively weaker than full version history and atomic rollback.

**Recommendation:** Continue scoped before/after hashes and backups now. Introduce Git only when Brennan decides version-control management is genuinely needed.

**Priority:** Medium.  
**Status:** Temporary controls active; Git deferred by user decision.

### G3 — Shared structured project knowledge

**Gap:** Workers exchange reports and Kanban comments, but there is no single curated V20 project knowledge layer automatically shared with every profile.

**Recommendation:** Create a compact, provenance-rich project knowledge index that points to canonical reports rather than copying raw content. Keep role memory separate from shared project facts.

**Priority:** High.  
**Status:** Not implemented.

### G4 — Deterministic lifecycle control

**Gap:** The controller and steward are bounded but partly LLM-driven.

**Recommendation:** Move required stage transitions into a small deterministic state machine:

```text
ADMISSION -> CONTRACT -> IMPLEMENT -> TRAIN -> BACKTEST -> REVIEW -> NEXT
```

Models decide research content. They must not decide whether mandatory safety stages may be skipped.

**Priority:** High.  
**Status:** Partially represented through Kanban dependencies; deterministic controller not implemented.

### G5 — Operator observability

**Gap:** The Live Team window is an initial custom view, not a complete operational console.

**Recommendation:** Finish live desktop verification; add heartbeat age, receipt/artifact links, cycle-level stage, bounded worker output, and clear blocked/handoff reasons. Keep it read-only.

**Priority:** High.  
**Status:** Initial implementation and tests complete; final live click-path and expanded receipts remain.

### G6 — Reproducible environment

**Gap:** The full V20 suite has unrelated environmental failures involving a missing `yfinance` dependency and Windows pytest temporary-directory permissions.

**Recommendation:** Freeze the actual supported environment, separate optional legacy dependencies, and use a known writable native pytest basetemp. Do not change the configured Massive data provider.

**Priority:** Medium.  
**Status:** Resolved 2026-07-23. The declared dependency was already present in the project `.venv`; the failures came from using the system interpreter. The supported Windows/Git-Bash command is now recorded in `README.md`. Verification with `.venv/Scripts/python.exe` and a native external basetemp produced `46 passed in 8.04s`; the temporary directory was removed and its absence verified.

### G7 — Usage, quota, and productivity accounting

**Gap:** Per-worker model usage, elapsed time, retries, and evidence productivity are not yet presented together.

**Recommendation:** Record model/provider, API calls, tokens where available, elapsed time, task verdict, artifact count, retries, and operator interventions for each task. Do not optimize for token minimization alone; optimize for verified useful output.

**Priority:** Medium.  
**Status:** Partial usage logs exist; consolidated view does not.

### G8 — Scheduler idempotency and recovery evidence

**Gap:** Cron and Kanban provide recurrence and task history, but an agent-level success message is not transactional proof of exactly-once execution.

**Recommendation:** Use immutable task IDs, run locks, one lease per worker, atomic state transitions where available, and explicit receipts for ambiguous or interrupted outcomes.

**Priority:** High.  
**Status:** Partially implemented through one-active-task limits and board records.

### G9 — Least-privilege worker tools

**Gap:** A broad ecosystem can degrade accuracy and enlarge the security surface when every worker receives every tool.

**Recommendation:** Keep the ecosystem broad centrally while enforcing task-specific tool allowlists, read/write roots, and provider authority. No worker should gain a tool merely because it is installed.

**Priority:** High.  
**Status:** Role instructions are scoped; systematic per-profile tool allowlists require audit.

### G10 — Scientific research foundation

**Gap:** Adjustment provenance, point-in-time universe validity, leakage-safe chronology, purge/embargo, untouched holdout, and accounting remain the dominant research blockers.

**Recommendation:** Complete data/evaluation admission before architecture expansion or paid training. Fail closed rather than silently falling back or repeatedly tuning a compromised holdout.

**Priority:** Critical.  
**Status:** Remediation pipeline active; no promotion justified.

### G11 — Platform portability

**Gap:** V20 worker contracts and orchestration are currently expressed in Hermes profiles, cron jobs, and Kanban state.

**Recommendation:** Keep task contracts, evidence schemas, role definitions, and acceptance gates in platform-neutral files where practical. Platform adapters should route work, not own scientific truth.

**Priority:** Medium.  
**Status:** Partially true through reports and project files; scheduling/profile state remains Hermes-specific.

### G12 — Security and prompt-injection resistance

**Gap:** Any broad plugin/tool ecosystem increases supply-chain and prompt-injection exposure.

**Recommendation:** Pin versions, audit plugins/MCP servers, use pairing/allowlists, exclude secrets from workspaces and memory, test malicious task artifacts, and sandbox disposable evaluation workers.

**Priority:** High.  
**Status:** Some controls active; benchmark adversarial suite not implemented.

---

## 6. Consolidated recommendation register

| ID | Recommendation | Current disposition |
|---|---|---|
| R01 | Keep Hermes as V20 orchestrator and Codex as primary worker intelligence. | Recommended now |
| R02 | Freeze platform migration for an evidence period rather than switching by reputation. | Recommended; benchmark may shorten uncertainty |
| R03 | Maintain a broad central ecosystem but narrow each worker's active tool schemas. | Recommended now |
| R04 | Audit and enforce per-profile and per-job tool allowlists. | Pending |
| R05 | Preserve Mnemosyne as Hermes's current memory provider. | Active user preference |
| R06 | Compare platforms under cold, controlled-memory, and native-memory conditions. | Included in benchmark plan |
| R07 | Do not run Hermes and OpenClaw concurrently against canonical V20. | Required safety boundary |
| R08 | Build OpenClaw only in an isolated lab with separate state, workspaces, ports, and channels. | Included in benchmark plan |
| R09 | Use the exact same model, reasoning level, task packet, time budget, and tool policy where possible. | Included in benchmark plan |
| R10 | Repeat trials because agent results are nondeterministic. | Three initial trials per task recommended |
| R11 | Score correctness, safety, autonomy/recovery, evidence, observability, latency, and operator burden. | Included in benchmark plan |
| R12 | Add deterministic stage gates around agentic research decisions. | Pending |
| R13 | Use disposable task workspaces and read-only source snapshots. | Pending; mandatory for benchmark |
| R14 | Finish the read-only Live Team dashboard before considering control actions. | In progress; control actions remain prohibited |
| R15 | Add per-worker usage and verified-productivity receipts. | Pending |
| R16 | Build a provenance-rich shared V20 knowledge index. | Pending |
| R17 | Fix environment reproducibility without reverting Massive to `yfinance`. | Pending |
| R18 | Resolve scientific admission before more model complexity or paid training. | Critical current priority |
| R19 | Keep GPU spending, paid services, broker access, execution, deployment, promotion, risk, and schedule changes human-gated. | Active boundary |
| R20 | Prefer OpenClaw if the primary goal becomes a broad personal/device assistant. | Conditional |
| R21 | Prefer OpenHands if the primary workflow becomes Git-centered, containerized software engineering. | Conditional |
| R22 | Treat Codex/OpenCode as coding workers, not complete autonomous operating systems. | Recommended framing |
| R23 | Do not interpret ecosystem size, stars, or demos as V20 performance evidence. | Required decision discipline |
| R24 | Preserve platform-neutral role contracts, task packets, schemas, and evidence whenever practical. | Recommended |
| R25 | Reassess the platform only after measured reliability failures or benchmark superiority. | Recommended switch gate |

---

## 7. Platform switch gates

A migration away from Hermes is justified only if a controlled comparison shows a material advantage in the dimensions that matter to Brennan, such as:

- higher acceptance-test correctness;
- fewer human interventions;
- materially better crash/restart recovery;
- stronger isolation or safety enforcement;
- simpler operation and maintenance;
- better truthful observability;
- lower latency or resource use without sacrificing quality;
- superior memory correction/retrieval under the native-memory track.

Do not switch because another project has more stars, more integrations, or a more polished demo. Do not retain Hermes merely because it is already installed.

---

## 8. Sources checked

Official sources checked on 2026-07-23:

- Hermes documentation: <https://hermes-agent.nousresearch.com/docs>
- Hermes repository: <https://github.com/NousResearch/hermes-agent>
- OpenClaw repository: <https://github.com/openclaw/openclaw>
- OpenClaw multi-agent documentation: <https://docs.openclaw.ai/concepts/multi-agent>
- OpenClaw memory documentation: <https://docs.openclaw.ai/concepts/memory>
- OpenClaw scheduled-task documentation: <https://docs.openclaw.ai/automation/cron-jobs>
- OpenClaw sandbox documentation: <https://docs.openclaw.ai/gateway/sandboxing>
- OpenClaw Windows documentation: <https://docs.openclaw.ai/platforms/windows>
- OpenHands repository: <https://github.com/OpenHands/OpenHands>
- OpenAI Codex repository: <https://github.com/openai/codex>
- OpenCode repository: <https://github.com/anomalyco/opencode>

Repository popularity was observed only as ecosystem context and is not used as evidence of task quality.
