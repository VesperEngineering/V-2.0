---
name: cross-agent-handoff
category: software-development
description: Write self-contained operating directives for another autonomous agent to audit, fix, and build on a codebase without needing to ask questions.
tags: [handoff, continuity, autonomous-agents, onboarding, documentation]
triggers:
  - user says "handoff for [agent name]"
  - user says "write a summary for [other agent] to continue"
  - user says "one-shot prompt" for another agent
  - user asks for "detailed summary" of project state for another agent
  - user is about to switch agents and needs continuity
  - project state changes significantly mid-session and needs to be captured
  - user says "going to switch" or "give this to [agent]"
---

# Cross-Agent Handoff Documents

Write a **self-contained operating directive** that enables another autonomous agent to audit, fix, and build on a codebase without asking questions. Not a reference manual — an actionable brief.

## Required Structure (in order)

### 1. THE MISSION (top 3 lines)
What the project is building and why. The vision — not the current state. One paragraph maximum.

### 2. WHERE WE ARE NOW (honest audit)
Two subsections, equal weight:

**What works** — bullet list of genuinely working features, with numbers
**What's broken (THE GAP)** — the single biggest problem called out explicitly with hard data. If there's a metric that shows the gap (e.g. "430/474 tickers have only 1 factor"), lead with it.

### 3. WHAT EXISTS (detailed inventory)
A table or structured list of every major component with: name, data source, ticker count, speed, status (✅/⚠️/❌).

Include a **critical insight** section — data the agent already owns but nobody is using. This is the highest-leverage finding.

### 4. HOW THINGS WORK (flow documentation)
Explain the pipeline end-to-end in plain language. Include:
- The data flow (source → processing → output)
- The scoring/combination logic (and its flaws)
- Configuration files and where they live

### 5. CRITICAL GOTCHAS (numbered, with code)
Anything that will break a new agent if they don't know it. For each:
- ⚠️ Severity marker
- The problem
- The fix (exact code or command)

### 6. THE ROADMAP (phased, ordered)
Phase 0 is always "fix what's blocking daily operations." Each phase has:
- Goal (one sentence)
- Specific actions with exact file paths
- Expected outcome (measurable)

### 7. SKILLS & TOOLS
What code to reuse, what data exists but is unused, what APIs are available with credentials.

### 8. USER PREFERENCES (at the bottom)
Communication style, decision-making approach, aesthetics, naming conventions.

## Key Principles

- **Every number must be real** — run the query, read the file, count the rows. No approximate digits.
- **Lead with the gap** — burying the bad news makes the agent waste time rediscovering it.
- **Phase 0 is always "fix the broken pipeline"** — nothing else matters until the basics run without errors.
- **Give exact file paths** — "fix `app/factors/sp500_technical.py`" not "fix the technical factor."
- **Include copy-paste commands** — every action the agent needs to take should have a ready command.
- **The agent will NOT remember this conversation** — the handoff must be fully self-contained.
- **Proactive prompt rule:** When the next gate requires another agent, draft the ready-to-send operating prompt automatically rather than asking Brennan whether they want one. Include mission, exact worktree, scope boundaries, RED→GREEN/verification gates, stop conditions, and explicit no-integrate/no-authority-expansion constraints. If a review fails, immediately draft the repair prompt with each verified blocker and its adversarial regression.

### Evidence-spine handoffs

For work that improves durable project memory or operational evidence, frame the assignment as an **audit-first, read-only evidence-spine contract**, not a generic memory project:

1. Name existing canonical authorities (board, manifests, receipts, provenance) and require classification as canonical, derived, or historical before code changes.
2. Permit a minimal typed read model only if the audit demonstrates a binding gap. Missing, stale, malformed, conflicting, or provenance-unbound evidence must classify as unavailable; the view must not repair, rewrite, or replace its sources.
3. Explicitly prohibit RAG, embeddings, vector stores, conversational persistence, provider calls, background agents, and authority expansion unless separately justified and authorized.
4. Use a separate worktree when the primary checkout has active work. Require source/date/schema-or-version/digest binding, focused adversarial tests, and independent review before calling the view authoritative.

## Common Pitfalls

- ❌ Writing a reference dump instead of a directive (no mission, no gap, no roadmap)
- ❌ Describing what the system should do rather than what it actually does now
- ❌ Omitting hard numbers (always run the query)
- ❌ Burying the gotchas — put them front and center
- ❌ Assuming the agent knows the project vision
- ❌ Calling it a "summary" or "reference" — the user wants an **operating directive**, not a reference manual

## Iteration Pattern

If the user says a prior handoff was "too technical" or "doesn't say what we're trying to do":
1. Lead with THE MISSION and THE GAP instead of the inventory
2. Make the roadmap phased, not a flat priority list
3. Add "WHERE WE ARE NOW" with honest strengths/weaknesses before the detailed inventory
4. End with user preferences so the agent knows how to communicate

When the user says "tear apart everything and fix what needs to be fixed" — the handoff must be an **audit → fix → build** directive, not a state report. Every strength/weakness must be backed by a real number run at the time of writing. The gap section should name the single biggest problem explicitly with the metric that shows it.

See `references/vesper-handoff-example.md` for the full Vesper handoff that successfully drove a 15-commit autonomous transformation (430→499 multi-factor tickers, 57K→2.4M OHLCV rows, 11→13 green cron jobs).

When a handoff involves named workers, specialist skills, Steward routing, or autonomous wake-up claims, run the configuration-versus-activity audit in `references/named-worker-flow-audit.md`. Do not equate profiles, installed skills, heartbeat cycles, or briefing jobs with actual dispatch.

## Parallel Session Ownership

When multiple Hermes windows are active, enforce **one session → one task → one branch/worktree**. Before trusting a handoff or resuming work:

1. Inspect the live worktree, staged diff, branch, and reflog first.
2. Use session history only to identify which window produced each state; historical summaries never override the filesystem.
3. If two sessions share a worktree, pause edits, name one owner, and stop only the conflicting session—not unrelated parallel sessions.
4. Require explicit approval before resetting another session's uncommitted work.
5. If safety review forces a scope downgrade, tell the user immediately and state which originally approved capabilities are no longer delivered. Do not silently substitute a shadow/read-only artifact for the requested workflow.

See `references/parallel-worktree-collision.md` for the collision-detection commands, evidence hierarchy, and safe resolution sequence.

## Verification

After writing, verify the handoff answers these questions for a new agent:
- What is this project building? (mission)
- What's the single biggest problem right now? (gap)
- What files do I need to touch first? (roadmap Phase 0)
- What will break if I don't know about it? (gotchas)
- What data exists that I don't know about? (critical insight)