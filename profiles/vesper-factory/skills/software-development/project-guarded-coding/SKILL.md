---
name: project-guarded-coding
description: Before editing any code in a project with skills, codegraph, or guardrail files, run the pre-flight checklist to avoid hallucination, missed context, and protocol violations.
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [software-development, guardrails, skills, codegraph, pre-flight]
    related_skills: [surgical-engineering, test-driven-development, requesting-code-review]
---

# Project Guarded Coding

## Overview

Many projects carry their own guardrails: Hermes skills, CodeGraph indexes, `AGENTS.md`, `SKILLS/CODE.md`, `EXAMPLES.md`, or similar coding-constitution files. Skipping them leads to hallucinated APIs, missed conventions, stale assumptions, and protocol violations.

This skill enforces a **pre-flight checklist** that must run before any code edit in a guarded project. It complements `surgical-engineering` by expanding step 1 ("read relevant implementation") into a mandatory discovery sequence.

## When to Use

Use **before editing any code, tests, build files, or configuration** when ANY of the following are true:
- The project has a `.codegraph/` directory (CodeGraph index exists)
- The project has `AGENTS.md`, `SKILLS/CODE.md`, `SKILLS/EXAMPLES.md`, or similar
- The project has `.hermes/skills/` or the active Hermes session has relevant skills
- You have previously been corrected for skipping skills or codegraph in this project

If none of the above apply, this skill adds no overhead.

## Pre-Flight Checklist (mandatory)

**Do not write or edit code until all applicable steps below are complete.**

### Step 0: Verify Workspace Ownership and Concurrent Activity

Before creating a branch/worktree or touching a candidate:

- Inspect the canonical branch/remote identity, dirty state, existing branches, and `git worktree list`.
- Check active task/session context when another authorized agent may be operating on the same repository.
- If the intended branch or worktree already exists, inspect its status and recent activity before deciding whether it is abandoned or actively owned.
- Never create a duplicate candidate or edit an actively owned worktree. Switch to a non-conflicting task such as read-only review, independent verification, or documentation, and let one agent retain write ownership.
- If a concurrent session advanced `main`, restart discovery from the new canonical HEAD; do not continue from the stale plan merely because pre-flight had already begun.

This is especially important for autonomous or multi-agent projects: an apparently missing implementation may already be under construction or integrated by another session between tool calls.

### Step 1: Load Relevant Skills

```
skills_list()  # or skills_list(category='...')
# For every skill whose description matches the task — even partially:
skill_view(name='<skill>')
```

- Err on the side of loading. Skills encode API endpoints, tool-specific commands, and proven workflows that outperform general-purpose approaches.
- If a skill is missing steps or has wrong commands, patch it immediately with `skill_manage(action='patch', ...)`.
- The system instructions explicitly require this: "Only proceed without loading a skill if genuinely none are relevant to the task."

### Step 2: Query the CodeGraph Index

If the project has `.codegraph/`:

```
# Verify index exists
codegraph status  # or ls -la .codegraph/

# Explore the exact symbols/files you plan to change
codegraph_explore(query="<symbol_names_or_natural_language_question>")
```

- `codegraph_explore` returns **verbatim on-disk source** plus blast radius (callers, callees, tests). Treat it as a Read you have already performed.
- Do not rely on memory or prior file reads alone. The index may have changed since your last read.
- In a linked worktree, confirm that CodeGraph is reading that worktree. If it reports results from a different worktree, initialize a local ignored index with `codegraph init -i`, then re-query the changed symbols. A parent-worktree index cannot verify files that exist only on the isolated branch.
- If the project has no index, consider running `codegraph init` before large edits.

### Step 3: Read Project-Specific Guardrails

Read these files in order of authority (highest first):

| File | Authority | What it governs |
|------|-----------|-----------------|
| `AGENTS.md` | Project constitution | Execution boundaries, denied/allowed authority, data rules, model constraints |
| `SKILLS/CODE.md` | Coding style | Principles: simplicity, surgical changes, goal-driven execution |
| `SKILLS/EXAMPLES.md` | Concrete precedent | Right/wrong patterns for each principle |
| `README.md` / `docs/` | Setup and architecture | How to run, test, and verify |

- If a planned change violates any example in `EXAMPLES.md`, stop and reconsider.
- `AGENTS.md` overrides general guidelines when they conflict.

### Step 4: Establish the Change Contract

Only now proceed to `surgical-engineering` step 1: read the relevant implementation, tests, and caller context. The prior steps ensure you are reading the **right** implementation with the **right** conventions.

## Why This Matters

| Failure Mode | Cost | Guardrail Prevented |
|--------------|------|---------------------|
| Edited code based on stale memory of file contents | Silent bug, wrong diff | CodeGraph re-reads verbatim source |
| Used wrong API because skill had the correct contract | Runtime error, revert | Skill loaded before editing |
| Violated project-specific data boundary (e.g. `/data` is read-only) | Data corruption, loss of trust | `AGENTS.md` read first |
| Overengineered because EXAMPLES.md has an anti-pattern for it | Bloat, review rejection | EXAMPLES.md checked before coding |
| Strategy factory hardcoded to one option, missed second | Engine crashes on config change | CodeGraph blast radius showed all callers |
| **Skipped skill loading and codegraph entirely** | Hallucinated changes, fabricated APIs, missed conventions, user frustration | This checklist |

### Critical: skipping the checklist is a first-class failure

If you are corrected by the user for **not loading skills**, **not using codegraph**, or **not reading project guardrails**, treat that correction as a workflow defect in your execution — not a minor oversight. The user explicitly stated: *"I cannot have an agent that doesn't load what is needed."* Encode this as a hard rule: **no code edit without loaded skills and queried codegraph.**

## Verification Checklist

Before declaring the pre-flight complete:

- [ ] Canonical HEAD/remote, dirty state, existing branches/worktrees, and concurrent ownership were checked.
- [ ] Relevant skills were loaded and inspected.
- [ ] CodeGraph index was queried for symbols to be changed (if index exists).
- [ ] `AGENTS.md` / `SKILLS/CODE.md` / `EXAMPLES.md` were read (if present).
- [ ] Change contract is defined with concrete success criterion.

## Session-Specific References

See `references/v20-pre-flight-pattern.md` for a concrete walkthrough of this checklist applied to the VESPER 2.0 codebase, including the exact commands used to initialize the CodeGraph index and the resulting artifact verification.
