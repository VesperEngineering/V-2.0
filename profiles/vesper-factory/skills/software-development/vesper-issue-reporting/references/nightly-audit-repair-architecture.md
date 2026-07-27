# Nightly Audit and Bounded Repair Architecture

Use this reference when implementing unattended issue discovery and overnight engineering work across multiple repositories.

## Separation of authority

Use two chained jobs rather than one self-authorizing agent:

1. **Read-only audit** discovers, verifies, deduplicates, updates issue registries, and generates a combined health briefing.
2. **Bounded repair** consumes the latest audit output, selects at most one eligible ordinary engineering defect, applies strict root-cause/TDD discipline, and leaves the issue at `Awaiting review`.

The discovering agent must not silently repair and close safety-critical findings in one pass. A passing focused test does not grant deployment or trading authority.

## Hermes cron pattern

- Cron sessions are fresh sessions; attach required skills explicitly.
- Set `workdir` to the primary repository so its `AGENTS.md` is injected and file/terminal operations resolve there.
- When auditing a second repository, name its absolute path and require reading its project rules explicitly; one `workdir` cannot inject both repositories' context files.
- Chain repair from audit with `context_from=[audit_job_id]` so the repair receives the latest completed audit output.
- Restrict audit toolsets to `file` and `terminal` unless another capability is demonstrably required.
- Use local delivery when Markdown files are the durable output. In a CLI-only session, local delivery does not create a live notification; inspect with `hermes cron list` or read the generated files.
- Jobs with a `workdir` run sequentially, which prevents process-global working-directory collisions.
- Keep prompts self-contained because cron runs without the current chat context.

## Multi-project files

Keep one authoritative registry per project and one generated combined briefing. Do not let every agent append to one shared free-form Markdown file.

Recommended shape:

```text
project-a/docs/ISSUES.md
project-b/docs/ISSUES.md
project-a/docs/DAILY_HEALTH.md
```

Each repository's `AGENTS.md` should point to its registry and require the reporting skill. New interactive CLI agents must start from the repository root for a cwd-only `AGENTS.md` to load.

## Audit completion checks

- Read both registries before adding findings.
- Distinguish current evidence from historical logs and cached test state.
- Treat missing evidence as degraded/unknown, never green.
- Treat dirty worktrees as context, not defects.
- Permit writes only to declared registry/briefing files.
- Read back every output and verify unique IDs, valid Markdown, and supported health claims.
- Never trigger the system merely to make an audit easier.

## Repair eligibility gate

A repair job should select at most one issue and skip when ownership or safety is unclear.

Eligible examples:

- Deterministic import or parsing defect
- Local validation bug
- Dashboard presentation or logging defect
- Focused failed unit test with no external effects

Ineligible without separate approval:

- Strategy/factor economic logic or weights
- Signals, portfolio construction, sizing, targets, or risk limits
- Broker/account/order paths or execution gates
- Scheduler configuration
- Provider/credential/dependency changes
- External ingestion, training, model artifacts, promotion, or deployment

## Bounded repair contract

- Inspect git status first and preserve unrelated work.
- Establish a deterministic RED reproduction before editing production code.
- Trace the root cause; do not patch symptoms.
- Limit the task to one issue and a small number of source/test files.
- Run the focused test RED, implement the smallest fix, rerun GREEN, then run the narrowest safe regression set.
- Do not commit, push, deploy, or mark `Verified closed` automatically.
- Update the issue to `Awaiting review` with root cause, changed files, and exact RED/GREEN evidence.
- A later independent audit or operator review owns closure.

## Surface and profile continuity

Hermes Desktop and CLI can share sessions, skills, memory, cron jobs, credentials, and configuration when they use the same Windows user and Hermes profile. The Desktop application does not need to remain open for CLI use. Avoid resuming the same session simultaneously in multiple windows; use separate titled sessions and isolated worktrees or explicit file ownership for parallel editors.