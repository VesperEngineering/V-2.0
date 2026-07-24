# V20 Platform Gap Authority Audit v1

**Audit time:** 2026-07-24T00:09:13-04:00  
**Task:** `t_185f09d6`  
**Scope:** Read-only audit of G1 worker isolation, G2 rollback evidence, G9 least-privilege tool exposure, and G12 security/prompt-injection resistance.  
**Authority:** Evidence and repair recommendations only. This report does not authorize profile, plugin, MCP, config, schedule, source, data, model, broker, risk, execution, provider, or capital changes.

## Classification

**Overall: PARTIAL**

| Gap | State | Decisive reason |
|---|---|---|
| G1 — Worker isolation | **ABSENT** | Every observed V20 Kanban task and enabled V20 cron job uses the same canonical V20 directory, and all seven worker profiles use the local terminal backend. Role instructions constrain intent but do not create a filesystem or process boundary. |
| G2 — Versioning and rollback | **PARTIAL** | Hashes and a redacted Hermes snapshot exist, but V20 is not a Git worktree, Hermes checkpoints default to disabled, and no general task-scoped restore drill is evidenced. |
| G9 — Least-privilege worker tools | **ABSENT** | All seven workers expose the same broad CLI toolset and the same command allowlist, including capabilities unrelated to most roles. The Kanban task schema has no observed per-task toolset field. |
| G12 — Security and prompt-injection resistance | **PARTIAL** | Secret redaction, context scanning, untrusted web/browser/MCP framing, smart approvals, no configured MCP, and no enabled plugins are evidenced; Tirith is fail-open, scanner coverage is bounded and bypassable in tested cases, and no V20 adversarial acceptance receipt exists. |

## Evidence boundary and method

Facts below come from the exact local files or read-only live commands named in each section. Credential values, `.env`, auth stores, raw memory, session transcripts, and private identifiers were not read or printed. The official Hermes documentation scrape failed with an upstream billing error, so current-runtime behavior is grounded in the installed Hermes source and live CLI output rather than an unverified documentation paraphrase.

The seven current V20 profiles are listed in `hermes-local/WORKERS.md:1-28`. Their runtime `SOUL.md` files were read from `C:/Users/bgonn/AppData/Local/hermes/profiles/<profile>/SOUL.md`. A SHA-256 comparison at audit time showed that all seven runtime identities match their corresponding entries in `hermes-local/manifest.json`.

## G1 — Worker isolation

**State: ABSENT**

### Exact evidence

1. `reports/agent_platform_strategy.md:176-183` records the gap as shared canonical-folder workers and says task-owned disposable workspaces are not implemented.
2. A read-only query of `C:/Users/bgonn/AppData/Local/hermes/kanban/boards/v20/kanban.db` found 14 tasks. All 14 have `workspace_kind = dir`; six store `C:/Users/bgonn/Desktop/v20` and eight store the equivalent backslash spelling `C:\Users\bgonn\Desktop\v20`. No task-owned `scratch` or `worktree` workspace was observed.
3. The current card `t_185f09d6` itself is `workspace_kind = dir` at `C:\Users\bgonn\Desktop\v20`.
4. Sanitized reads of all seven worker configs show `terminal.backend = local`, `terminal.cwd = .`, and `docker_mount_cwd_to_workspace = false`.
5. The five enabled V20 jobs in the default cron store all use `C:\Users\bgonn\Desktop\v20` as `workdir`. The paused `v20-bounded-model-iteration` job uses the same path.
6. The worker identities impose authority and write-scope rules. Examples include protected-data read-only rules in `v20-data-engineer/SOUL.md:24-27`, implementation scope in `v20-development/SOUL.md:12-27`, and no self-review in `v20-risk-review/SOUL.md:12-27`. These are important behavioral controls, but none is an OS-enforced read-only mount, separate user, container boundary, or task-owned writable root.
7. The board has task/run/event evidence—claims, heartbeats, blocks, completions, and one-active-task routing intent—but leases and role separation do not prevent two processes from writing the same file.

### Decisive blocker

A worker with `file` or `terminal` access can reach the same canonical directory as every other worker. There is no evidenced control that blocks an out-of-scope write at the filesystem boundary. Prompt-level authority therefore remains the primary defense against conflicting or unauthorized writes.

### Smallest safe correction

For every dispatched worker, create a task-owned disposable workspace. Mount or copy an immutable, allow-listed V20 source snapshot read-only, provide one task-specific writable output directory, and do not expose the canonical V20 directory as writable. Because V20 is currently non-Git, this can be implemented without adopting Git by using a deterministic snapshot plus an isolated sandbox/container or OS ACL. Merge only reviewed artifacts through a separate authorized handoff.

### Verifiable acceptance gate

Run two concurrent canary tasks under different V20 profiles and record:

- distinct `HERMES_KANBAN_WORKSPACE` paths;
- a successful write inside each task's authorized output root;
- a denied write attempt against canonical `C:/Users/bgonn/Desktop/v20` and the other task's workspace;
- identical before/after SHA-256 manifest for canonical V20;
- no shared writable mount, environment path, or process-owned temporary directory;
- cleanup of both disposable workspaces after their receipts are preserved.

A SOUL instruction or a worker's statement that it stayed in scope is not acceptance evidence.

## G2 — Versioning and rollback

**State: PARTIAL**

### Exact evidence

1. `git rev-parse --is-inside-work-tree` and `git status --short` both returned `fatal: not a git repository` from `C:/Users/bgonn/Desktop/v20`.
2. `reports/agent_platform_strategy.md:185-192` records that Git is deferred by Brennan's decision and that hashes/backups are temporary controls rather than full version history or atomic rollback.
3. The installed Hermes `DEFAULT_CONFIG` reports `checkpoints.enabled = false`, with a maximum of 20 snapshots only if enabled. None of the seven worker config files contains a `checkpoints` override.
4. `hermes-local/README.md:1-11` describes a read-only, redacted Hermes snapshot and explicitly excludes credentials, auth, databases, sessions, logs, caches, backups, binaries, runtime locks, and Hermes application source/venv.
5. `hermes-local/manifest.json:2-16` records `active_runtime_modified: true`, creation time `20260724T014840Z`, and the same exclusions. The manifest contains 4,326 entries. All seven current runtime `SOUL.md` hashes matched the manifest during this audit.
6. The snapshot provides identity/configuration integrity evidence but is not a complete V20 source rollback point. Its redacted config cannot restore credentials by design, and its manifest excludes backups and Hermes runtime source.
7. `.hermes/plans/2026-07-23_172130-hermes-openclaw-benchmark.md:339-355` requires SHA-256 manifests, timestamped backups, allow-listed copies, secret rejection, read-only snapshot files, and deterministic-hash tests for the proposed benchmark. That is a plan, not evidence that every current V20 task has such a backup or that restore has been exercised.
8. Artifact-specific SHA-256 receipts exist, including `models/xgb_ranker.metadata.json` and research manifests. These prove selected artifact identity, not restoration of the project, profile configuration, or a failed multi-file change.
9. No general task-scoped pre-change backup, post-change manifest, atomic restore receipt, or measured recovery drill was evidenced for the current board.

### Decisive blocker

Current hashes can detect some drift but do not prove recoverability. A redacted snapshot and scattered artifact hashes cannot reconstruct an arbitrary multi-file task state, and checkpoints are not enabled.

### Smallest safe correction

Keep the non-Git decision intact. Standardize one task receipt for every authorized mutation containing: task ID, exact allowed paths, pre-change path/size/SHA-256 manifest, timestamped backup location, post-change manifest, restore command, and retention/cleanup rule. The backup must be outside protected data and must contain only the files within the approved change scope.

### Verifiable acceptance gate

In a disposable canary workspace:

1. create a pre-change manifest and timestamped backup for a two-file scope;
2. mutate both files and verify the post-change hashes differ;
3. interrupt the simulated task between the two writes;
4. restore using only the receipt and backup;
5. verify byte-for-byte equality with every pre-change hash;
6. record command, exit code, elapsed recovery time, and backup cleanup result.

A backup-created message without a successful restore comparison fails the gate.

## G9 — Least-privilege worker tools

**State: ABSENT**

### Exact evidence

1. `reports/agent_platform_strategy.md:36-55` requires a broad central toolbox but a narrow role-specific toolbelt. `reports/agent_platform_strategy.md:254-261` says systematic per-profile allowlists require audit.
2. Live `hermes --profile <name> tools list` output was identical for all seven V20 workers. Each enabled: `web`, `browser`, `terminal`, `file`, `code_execution`, `vision`, `image_gen`, `tts`, `skills`, `todo`, `memory`, `session_search`, `clarify`, `delegation`, `cronjob`, and `computer_use`.
3. Those schemas materially exceed the normal role matrix in `reports/agent_platform_strategy.md:48-55`. For example, Risk Review receives browser automation, code execution, image generation, speech, delegation, cron management, desktop control, memory mutation, terminal, and writable file operations despite being specified as a read-only reviewer.
4. Every worker config maps CLI to the broad `hermes-cli` platform toolset. No role-specific CLI toolset was observed.
5. Every worker config carries the same `command_allowlist`, including categories labelled `script execution via -e/-c flag`, `execute_code`, `overwrite system config`, `recursive delete`, `hermes update`, `git reset --hard`, and `git force push`. A benign audit heredoc was auto-approved under the script-execution category, proving the allowlist is active for at least that class. Destructive probes were not run, so their executable reach is **not evidenced**; their configured presence is itself inconsistent with least privilege.
6. The V20 Kanban `tasks` schema contains `skills` and `model_override` but no `enabled_toolsets`, disabled-toolsets, read/write roots, or provider-authority field. Task-specific tool restriction through the current board is therefore **not evidenced**.
7. Current cron evidence is narrower: the five enabled V20 jobs in the default cron store explicitly set `enabled_toolsets = [terminal, file]`. The paused `v20-bounded-model-iteration` job has no explicit toolset restriction but is disabled. All seven worker-profile cron stores report no jobs.
8. `hermes mcp list` reports no MCP servers for each V20 worker. Parsed `hermes plugins list` output reports 86 plugin rows per worker and zero enabled rows; the one non-bundled row, `mnemosyne` version 0.5.0, is reported `not enabled` by that command. Memory-provider behavior is separate and was not changed or reclassified by this audit.
9. SOUL authority limits are specific and generally strong, but advisory instructions do not remove tool schemas or OS permissions.

### Decisive blocker

The exact same broad, writable, networked, scheduling-capable tool surface is exposed to every worker, including independent Risk. The command allowlist further weakens approval friction. Least privilege is therefore not an enforced worker property.

### Smallest safe correction

Define and pin a minimal CLI toolset per V20 profile. Remove clearly irrelevant worker capabilities first: browser automation, image generation, TTS, computer control, cron management, delegation, and mutable memory unless a role-specific task contract proves need. Keep Kanban coordination injected only for assigned board workers. For read-only roles, pair the reduced schema with OS-enforced read-only roots because `file` and `terminal` are otherwise write-capable. Replace the shared command allowlist with role-specific approvals that never pre-allow destructive/system/config/history-rewrite classes.

### Verifiable acceptance gate

For each profile, launch a fresh dispatched canary and save the actual tool-schema names presented to the model. Verify that:

- the schema exactly matches an approved role matrix;
- `cronjob`, `computer_use`, mutable memory, deployment/provider tools, and other non-role tools are absent rather than merely prohibited by prose;
- an unauthorized tool call is rejected as unavailable;
- a write outside the approved root fails at the OS/sandbox layer;
- destructive/system/config command classes require a human approval or are denied;
- the five enabled V20 cron jobs remain limited to their explicitly approved toolsets;
- no task gains a tool merely because a plugin or MCP is installed centrally.

## G12 — Security and prompt-injection resistance

**State: PARTIAL**

### Exact evidence

1. The installed Hermes `DEFAULT_CONFIG` has `security.redact_secrets = true`, `security.tirith_enabled = true`, `approvals.mode = smart`, and `approvals.cron_mode = deny`.
2. The same defaults also have `security.tirith_fail_open = true` and the website blocklist disabled. None of the seven worker configs pins a `security`, `approvals`, or `checkpoints` section, so their posture depends on installed defaults.
3. `agent/prompt_builder.py:38-74` scans `AGENTS.md`, `.cursorrules`, and `SOUL.md` with shared threat patterns and replaces a matching file with a blocked placeholder before it reaches the system prompt.
4. A direct in-memory test of the actual `_scan_context_content` wrapper blocked `ignore all previous instructions` and safely stripped a leading UTF-8 BOM from benign text.
5. `tools/threat_patterns.py:49-59,207-255` caps scanning at 65,536 characters, normalizes NFKC, detects selected invisible characters, and explicitly documents that cross-script confusables are not covered.
6. In-memory audit probes detected classic instruction override, a hidden HTML div, and role hijack. They did not detect an injection appended after the 65,536-character scan cap or a Cyrillic-confusable spelling of `ignore`. These are bounded scanner findings, not proof that the model would obey either payload.
7. `agent/tool_dispatch_helpers.py:460-620` wraps long results from web, browser, and MCP tools in untrusted-data delimiters, neutralizes forged delimiter tokens, and records advisory threat findings. The scan metadata does not block or redact the normal result, and results shorter than 32 characters are not wrapped.
8. `agent/prompt_builder.py:597-607` tells computer-use sessions not to follow instructions in screenshots or web pages and not to type secrets. This is model guidance, not a content-enforcement boundary for image pixels.
9. `run_agent.py:2664-2745` applies secret redaction to text content before optional JSON session persistence. The default has redaction enabled, but no V20 receipt testing representative secret formats was found.
10. No MCP servers are configured and no plugins are reported enabled for the seven workers, reducing current external tool supply-chain exposure.
11. The five enabled V20 cron jobs use only `terminal` and `file`; controller/steward prompts explicitly bound work to V20 and prohibit broker/execution, protected authority classes, and unsupported progression. However, those jobs still work in canonical V20 and prompt rules do not sandbox terminal/file behavior.
12. No V20 adversarial suite or current pass receipt was found for poisoned files, long-tail injection, Unicode confusables, web/tool results, MCP/plugin output, memory/skill writes, screenshot text, secret redaction, or Tirith-unavailable behavior.

### Decisive blocker

The current posture combines useful defense-in-depth with fail-open and advisory elements. Tirith may fail open; regex scanning deliberately stops at 65,536 characters and misses tested confusables; UI defense is instruction-based; and worker tool/command exposure makes any successful injection more consequential.

### Smallest safe correction

First reduce worker tools as required by G9. Then pin security settings per V20 profile, prove Tirith is installed and healthy, and only then change its failure policy to fail closed for high-risk external/context paths. Add a small deterministic V20 adversarial regression set covering the observed scan cap/confusable gaps, forged delimiters, short external results, poisoned context files, screenshot instructions, and representative synthetic secret formats. Keep MCP empty and plugins disabled unless a separately reviewed, pinned dependency is approved.

### Verifiable acceptance gate

A fresh isolated worker must produce a signed/hashed test receipt showing:

- poisoned `AGENTS.md`/`SOUL.md` content is blocked before prompt assembly;
- payloads at the start, middle, and end of content larger than 65,536 characters are detected or safely delimited;
- Unicode invisible and cross-script-confusable variants are rejected or normalized under a documented policy;
- forged untrusted-result delimiters cannot escape framing;
- browser/web/MCP/plugin-style and screenshot-origin instructions cannot trigger an unapproved tool action;
- synthetic secrets are redacted from tool output and persisted logs;
- unavailable or timed-out Tirith causes the declared fail-closed result;
- an unauthorized filesystem, config, schedule, provider, or execution action is denied by capability/OS enforcement, not only by model refusal.

## Decisive blockers

1. Shared writable canonical V20 path for all workers and enabled V20 cron jobs.
2. No general task-scoped restore proof; checkpoints disabled and Git absent by decision.
3. Identical broad tool schemas and command allowlists across all seven worker roles.
4. Security scanner and Tirith posture remain partly fail-open/advisory, with tested coverage gaps and no V20 adversarial pass receipt.

## Residual risk

Even after the smallest corrections, local Windows workers will still share a host account and kernel unless stronger process/user isolation is adopted. Tool reduction cannot make `terminal` read-only by itself. Snapshot rollback remains weaker than versioned history and atomic merge. Pattern scanners cannot establish semantic safety against novel injection; containment must come from narrow capabilities, immutable inputs, explicit authority, and independently verified side effects.

## Next owner

**`v20-product`** — convert the four corrections and acceptance gates above into one exact-scope proposal for Brennan. After explicit authority for profile/config/workspace changes is recorded, route implementation to `v20-development` and require an independent Risk re-audit. This verdict does not authorize those mutations.

PASS_TO_IMPLEMENT
