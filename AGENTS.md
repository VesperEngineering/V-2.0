# VESPER 2.0 Agent Rules

Scope: `C:\Users\bgonn\Desktop\v20` and descendants unless a nested `AGENTS.md` overrides it.

## Communication

- when replying or giving information, be extremely concise and sacrifice grammar for the sake of concision.
- Always use plain language. Prefer familiar words and short sentences.
- For routine verification updates, use the shortest useful statement, e.g.
  `I’ll verify the live V20 code and vault.` Do not add process commentary unless
  it changes the user’s decision or understanding.
- When using jargon (for example, "shadow" or "failed close"), add one plain-English line explaining what it means, why it matters, and what choice it affects.
- Lead with the outcome. State uncertainty, blockers, and verification plainly.
- Never claim completion when a required check failed, was skipped, or was unavailable.

## Native Agent Routing

- Use `profiles/native/`, `vesper/platform/`, and approved `knowledge/` notes. Never use retired external-agent profiles or snapshots.
- Code or configuration edits: consult `knowledge/skills/v20-engineering.md`.
- Data, model, strategy, or factor work: also consult `knowledge/skills/v20-quant-research.md`.
- Durable knowledge: consult `knowledge/skills/knowledge-governance.md`.
- Agent handoffs: consult `knowledge/skills/v20-agent-handoff.md`.

## Product and Safety

- Default strategy: `ml_model`; `momentum` is also supported. Add no strategy unless explicitly requested.
- Build a lean, understandable quant system. Prefer clarity over speculative features.
- Never modify, delete, move, or write under `vesper/data/massive/` or `vesper/data/model_research/`.
- Treat Massive data as a read-only external dependency.
- Models and strategies must fail closed. Never silently fall back, fabricate, or substitute artifacts.

## Authority

- Approval required: broker, provider, account, or credential access or changes.
- Approval required: risk limits, trading parameters, orders, positions, capital allocation, or live deployment.
- Approval required: scheduler changes; paid compute/providers; GPU/cloud training.
- Approval required: protected-data writes; model training, family changes, promotion, or active-artifact replacement.
- Approval required: destructive file actions or broad cleanup.
- Allowed: inspection, tests, documentation, narrow non-critical fixes, read-only research, read-only feed/pipeline work, and other authorized local reversible work.

## Credentials

- Discuss credentials in private chat only when required.
- Never place credentials in files, patches, commands, logs, tests, screenshots, artifacts, Git history, external messages, or public displays.
- Outside chat, use redacted values. Possession never authorizes use, validation, rotation, or changes.

## Evidence

- Inspect the final diff and run the smallest meaningful verification required by the routed skill.
- Separate actual results from assumptions; state the exact blocker and next safe action.
- Never fabricate output or evidence.

## Task Closeout

- A task is not silently done while source changes remain dirty. Before closeout, classify every `git status` entry as committed, handed off, or explicitly parked in the final report.
- Run `uv run --locked python scripts/cleanup_completed.py --path <worktree> --done` for closeout; it first requires clean Git source, then removes only allowlisted generated output automatically.
- Use `--apply` only for an explicit generated-only cleanup before closeout, after confirming no active build or test uses the path.
- The cleanup command may remove generated `target/`, pytest/cache, temp, CodeGraph, state, and `*.egg-info` directories only. It must never remove source, a whole worktree, credentials, or protected data.
- Remove a completed clean linked checkout with `git worktree remove <path>`; do not delete worktree directories manually. Keep the branch if its commits may still be needed.

*Last updated: 2026-08-05.*
