# Vesper Worker Profiles

Vesper runs as an internal quant-firm team with durable named worker profiles.
Each is a separate Hermes profile with its own identity, session history, skills,
memory, and fail-closed authority boundaries.

## Team Hierarchy

```
Brennan (Founder/CEO)
  └─ Thomas — Managing Partner / COO
       └─ Clarke — Managing Agent (Hermes assistant)
            ├─ Morgan — Portfolio & Risk Architect
            ├─ Riley — Skeptical Red-Team Reviewer
            └─ Rez — Research & Evidence
```

Roles above Clarke are human-adjacent: Brennan owns the firm, Thomas owns
operations and can authorize critical/high work across all domains. Specialist
workers (Morgan, Riley, Rez) are dispatched by the Managing Agent, run
read-only first, and report evidence.

## Creating a Worker Profile

Profiles live under `~/.hermes/profiles/<name>/`. Create with:

```bash
hermes profile create <name> --clone-from default
```

This clones config, `.env`, `SOUL.md`, and skills from the default profile.

**Essential setup after creation:**

1. **Write `SOUL.md`** at `~/.hermes/profiles/<name>/SOUL.md`:
   - Role identity (who they are, who they report to)
   - Authority boundaries (what they can/cannot approve)
   - Team context (who else works here, current priorities)
   - Voice (direct, evidence-first, no cheerleading)

2. **Set max_turns** (autonomous COO and steward work needs high limits):
   ```bash
   hermes config set agent.max_turns 0 --profile <name>
   ```
   (0 = unlimited)

3. **Grant necessary skills.** Cloned from default already. For Vesper
   workers, `vesper-factor-workflow` is the canonical operational skill.

4. **Resolve model/provider** on first launch or via one-shot query.

## Worker Posture Rules

- **Read-only first.** Every worker's first assignment is a read-only audit.
  No file edits, broker access, scheduler mutation, or model promotion until
  explicitly authorized.
- **Evidence-first reporting.** Return exact file paths and line ranges for
  every finding. Severity labels: Critical, High, Medium, Low.
- **Concise briefs.** Previous reports were truncated by context limits.
  Target 3-5 highest-severity findings, not a comprehensive inventory.
- **Fail-closed.** If a check fails or data is unavailable, report the
  blocker, do not proceed with downstream work.

## Team Knowledge Journal

All autonomous sessions contribute to `D:/vesper/.hermes/learnings.jsonl`
— an append-safe JSONL file. Each team member adds one JSON line per session:

```json
{"ts": "2026-07-14T21:10:00Z", "from": "morgan", "type": "discovery",
 "topic": "covariance_validation", "note": "Ledoit-Wolf passes unit tests"}
```

Types: `discovery`, `blocker`, `decision`, `briefing`, `pipeline`, `system`.

Read the last 5 lines on session start. Append a summary on finish. This
persists knowledge across isolated cron sessions since Hermes memory is
disabled for cron jobs by default.

## Model Allocation

Each worker profile uses a model matched to their task complexity and cost. ChatGPT Pro OAuth via `openai-codex` provider works headlessly in cron jobs — no browser needed after initial auth (tokens persist and auto-refresh).

| Worker | Profile | Model | Provider | Cost Model |
|--------|---------|-------|----------|------------|
| **Thomas** (COO) | `vesper-thomas` | GPT-5.6 Sol (xhigh reasoning) | `openai-codex` | ChatGPT Pro (included) |
| **Morgan** (Risk) | `vesper-morgan` | GPT-5.6 Sol | `openai-codex` | ChatGPT Pro (included) |
| **Riley** (Red-Team) | `vesper-riley` | GPT-5.6 Sol | `openai-codex` | ChatGPT Pro (included) |
| **Rez** (Research) | `vesper-rez` | DeepSeek V4 Pro | `openrouter` | Pay-per-use |
| **Clarke/Steward** | `default` | DeepSeek V4 Flash | `openrouter` | Cheapest |

Override per-cron-job model with `cronjob update --model '{"model":"...","provider":"..."}'. Cron jobs using `openai-codex` work without interactive auth; the stored device-code OAuth token handles refresh.

Thomas can adjust reasoning at session start: `/reasoning medium` for lighter work, `/reasoning xhigh` for hard problems — both within the ChatGPT Pro subscription. All Sol profiles share the same OAuth credential pool.

## Launching Workers

```bash
# Interactive session
hermes chat -p <name>

# Quick query (non-interactive, good for one-shot tasks)
hermes chat -p <name> -q "Brief instruction" --model "deepseek/deepseek-v4-pro"

# Background session (output collected by the process manager)
hermes chat -p <name> -q "..." --model "..." &

# Resume a previous session
hermes --resume <session_id> -p <name>
```