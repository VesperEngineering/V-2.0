---
name: engineering-preparation
description: Mandatory pre-flight protocol before editing code in any project. Load skills, query codegraph, read guardrails, state assumptions. Prevents agents from acting on stale memory or missing critical context.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [software-development, pre-flight, guardrails, skills, codegraph]
    related_skills: [surgical-engineering, test-driven-development, systematic-debugging]
---

# Engineering Preparation

## Overview

Every agent MUST run this protocol before writing or editing code, tests, configuration, or build files. Skipping it produces hallucinated changes, missed conventions, broken imports, and fabricated artifacts. The user explicitly demanded this as a non-negotiable guardrail.

This skill governs what happens **before** `surgical-engineering` takes over. It does not replace surgical-engineering, TDD, debugging, or code review — it ensures those skills have accurate context to work with.

## When to Use

Use at the start of any task that involves:
- Editing source code
- Modifying tests or configuration
- Adding features or bug fixes
- Refactoring existing code
- Any task where the user says "change X" or "implement Y"

## The Pre-Flight Checklist

**Do not skip any step. Do not assume a task is "too simple" to need this.**

### Step 1: Load Relevant Skills

1. Call `skills_list()` to see available skills.
2. Load any skill that matches the task — even partially. Err on the side of loading.
3. If a skill is missing steps, has wrong commands, or needed a pitfall you discovered, patch it immediately with `skill_manage(action='patch')`.
4. If no loaded skill covers the class of work, consider creating or updating an umbrella skill after the task completes.

**Why this matters:** Skills encode API endpoints, tool-specific commands, proven workflows, and project-specific conventions. General-purpose reasoning cannot outperform a skill that was built from prior successful sessions. An agent that skips skill loading acts from stale general knowledge and invents incorrect approaches.

### Step 2: Query the CodeGraph Index

1. Check if the project has a `.codegraph/` directory (`find . -maxdepth 2 -type d -name '.codegraph'`).
2. **If no index exists, initialize one:** run `codegraph init` in the project root before editing. A non-trivial project without an index is a blind-edit risk.
3. If an index exists, call `codegraph_explore` on the exact symbols, files, or questions relevant to your planned change.
4. Re-query after any significant edit to verify blast radius before the next edit.

**Why this matters:** Codegraph returns verbatim source, call paths, and blast radius in one call. It prevents edits based on memory or stale file reads. The user explicitly demanded this after an agent edited `engine.py` without realizing the model artifact was a transformer, not XGBoost — a mistake that codegraph would have caught immediately.

### Step 3: Read Project Guardrails

1. Read `AGENTS.md` if it exists at project root. This is the highest-authority project constitution.
2. Read any project-specific coding standards (e.g., `SKILLS/CODE.md`, `docs/CODING_STANDARDS.md`).
3. Read `EXAMPLES.md` or equivalent reference files that show concrete right/wrong patterns.
4. If `AGENTS.md` does not exist but the project has `SKILLS/` or `docs/`, consider proposing one to the user.

**Why this matters:** Project guardrails contain authority boundaries (what you are allowed to change), data boundaries (what you must not touch), and style boundaries (how to match existing code). Violating them wastes user time and requires reverts.

### Step 4: State Assumptions Explicitly

Before implementing:

1. List your assumptions about file formats, data schemas, scope, and behavior.
2. If multiple interpretations exist, present them — do not pick silently.
3. If something is unclear, stop. Name what's confusing. Ask the user.
4. If a simpler approach exists, say so. Push back when warranted.

**Why this matters:** Hidden assumptions are the #1 cause of incorrect implementations. See `surgical-engineering` and `EXAMPLES.md` for concrete patterns of hidden assumptions and how to surface them.

## Native ABI / OS Interface Gate

When a task requires a native, undocumented, version-sensitive, or manually packed OS API (for example `ctypes` bindings, kernel/NT directory records, ioctl payloads, or a struct whose offsets are not enforced by the language runtime):

1. **Do not infer a wire layout from memory.** Locate installed headers/docs where possible, but treat them as incomplete until the call is exercised.
2. **Build an isolated, disposable probe first.** Create a temporary fixture with known names/data, bind only the proposed API and layout, invoke it, and validate every parsed offset/length against the known fixture.
3. **Make the parser fail closed.** Validate returned byte counts, record boundaries, alignment/next offsets, string lengths/encoding, and unexpected statuses before consuming data.
4. **Preserve the probe result in implementation or test evidence.** State the verified API class, offsets, and host/architecture scope.
5. **If the probe cannot safely verify the layout, stop.** Keep the feature unimplemented and report the exact ABI/layout blocker rather than guessing.

For filesystem security work, this gate does not replace semantic checks: use the pinned handle as the capability, enumerate relative to that handle, open direct children relative to it, reject reparse entries, and verify content identity after opening.

## Verification

Before declaring "preparation complete":

- [ ] At least one relevant skill was loaded and inspected.
- [ ] Codegraph was queried if an index exists (or initialization was attempted for non-trivial projects).
- [ ] Project guardrails were read if they exist.
- [ ] Material assumptions were stated or ambiguities were surfaced to the user.
- [ ] The requested behavior and success criterion are concrete and checkable.

## Common Pitfalls

1. **"This task is too simple to need skills."** No task is too simple. A 2-line config change can break a CI pipeline if you don't know the project's config conventions.
2. **"I already read that file earlier in the session."** File contents change. Other agents edit them. Your memory is not a source of truth. Re-read files via codegraph or read_file before patching.
3. **"Codegraph is overkill for a small fix."** Small fixes are where blast-radius surprises hurt most. A 1-line patch that drops a neighboring line because you didn't read the enclosing block is a regression.
4. **"I'll load skills after I see what the code looks like."** By then you've already formed an implementation plan from general knowledge. Load skills first so they shape your plan.
5. **"The project has no AGENTS.md, so I can skip guardrails."** Look for `.cursorrules`, `CONTRIBUTING.md`, `docs/CODING_STANDARDS.md`, `SKILLS/CODE.md`, `SKILLS/EXAMPLES.md`, or any `README` section about conventions.
6. **"I read the file with offset/limit, so I know what's there."** Pagination truncates content. Always re-read the full file (or the enclosing function block) before applying a patch, especially after prior edits in the same file.

## Session Example

**User:** "Wire up the Massive data feed in v20."

**Wrong (what agents do without this skill):**
- Jump straight to `feed.py`
- Edit based on memory of how feed.py looked
- Miss that `engine.py` hardcodes `momentum` as the only strategy
- Miss that the model artifact is a transformer, not XGBoost
- Deliver a technically correct feed adapter that doesn't solve the real problem

**Right (following this skill):**
- Load `skills_list()` → find `vesper-factor-workflow`, `surgical-engineering`, `massive-websocket-stream`
- Load all three
- Query codegraph: `codegraph_explore(projectPath=".", query="feed.py create_feed get_bars")`
- Read `SKILLS/CODE.md.txt` and `SKILLS/EXAMPLES.md`
- Read `config/settings.yaml` to see provider config
- Discover `engine.py` only supports `momentum`
- State assumption: "I'll add MassiveFeed to feed.py and wire it in create_feed, but engine.py strategy factory needs separate work"
- Implement with full context

## Related Skills

- `surgical-engineering` — governs how to make minimal, evidence-based edits.
- `test-driven-development` — governs RED → GREEN → REFACTOR cycles.
- `systematic-debugging` — governs root-cause investigation before fixing.
- `requesting-code-review` — governs pre-commit review gates.

---

*Created after user correction: "I cannot have an agent that doesn't load what is needed. I need at least 1 guardrail so that you don't make anything up."*
