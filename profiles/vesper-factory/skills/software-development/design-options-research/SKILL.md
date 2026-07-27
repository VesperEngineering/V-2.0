---
name: design-options-research
description: Use when the user asks to research, compare, or choose among design, UX, visualization, or implementation approaches before committing to one. Governs how to surface reviewable options, capture tradeoffs, and obtain explicit direction before writing production code.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [any]
metadata:
  hermes:
    tags: [design, ux, research, options, review, visualization, tkinter, gui]
    related_skills: [vesper-tkinter-ui-engineering, sketch, claude-design, plan, engineering-preparation]
---

# Design Options Research

## Overview

Use this skill when the user asks you to *research* a better way to display, organize, or implement something, or when they explicitly want to compare approaches before picking one. The goal is to give the user a small set of clear, reviewable choices with honest tradeoffs—not to silently implement the first reasonable idea.

This applies to UI layouts, data visualizations, interaction patterns, module boundaries, and any other decision where the user benefits from seeing alternatives.

## When to Use

Use for requests like:

- "Research a better way to display X."
- "What direction do people go for Y?"
- "Compare A, B, and C for me."
- "I want to see options before we commit."
- "Make this more informative / visual / usable."

Do not use when:

- The user explicitly says "implement X" or "do it."
- The request is purely factual and has no design space.
- The user has already approved a direction in the same thread.

## Workflow

### 1. Clarify the goal

Before generating options, confirm in one sentence what the user wants the design to achieve. Common angles:

- information density (more data vs. clearer hierarchy)
- growth over time (showing progression)
- interpretation (explaining what the data means)
- comparison (base vs. variant, before vs. after)
- authority/safety (what the display must not imply)

If the goal is ambiguous, ask a single narrowing question or state your assumption explicitly.

### 2. Generate 2–4 distinct options

Each option should be a different *stance*, not a cosmetic tweak. For each option include:

- **Name** (one or two words)
- **What it is** (one sentence)
- **Best for** (when this option wins)
- **Tradeoff** (what it costs)

Avoid options that are obviously worse; every candidate should be defensible.

### 3. Add a concise recommendation

State which option you recommend and why, in one or two sentences. Tie the recommendation back to the clarified goal.

### 4. Wait for explicit selection

Do not implement, write tests, update README, or create repository files until the user picks an option or says "do what you think is best." A response like "Yes please" to a recommended option counts as selection.

If the user says "I like that" or "go with B," treat it as authorization to implement that option.

### 5. Implement only the selected option

Once selected, implement cleanly. Do not leave half-implemented alternatives in the codebase. Verify as usual: compile, test, lint, and inspect the actual artifact.

## Common Pitfalls

1. **Implementing the first reasonable option.** When asked to research, the deliverable is the comparison, not the code.
2. **Presenting one option disguised as three.** Recolors or minor label changes are not distinct design stances.
3. **Omitting tradeoffs.** A choice without costs is not a real choice.
4. **Skipping the recommendation.** Users want your judgment, but they want it after seeing alternatives.
5. **Adding scope before selection.** Do not attach tests, docs, or unrelated polish to a research deliverable.
6. **Treating "research" as a web search only.** Useful research often includes a synthesized recommendation and, when appropriate, a throwaway mockup or sketch.

## Output Format

Keep the option list short and scannable. A good response shape:

```
Goal: [one sentence]

Option A: [name]
- What: ...
- Best for: ...
- Tradeoff: ...

Option B: [name]
...

Option C: [name]
...

Recommendation: [option] because ...

Do you want me to implement [recommended option]?
```

## When Visualization Is the Topic

If the user wants to see something "grow over time while also interpreting it," the standard professional pattern is a **time-series chart with annotations** (e.g., TensorBoard, Weights & Biases). For a lightweight Tkinter desktop app, the equivalent is a **Canvas-based node-link graph** or a **sparkline with caption panel**.

See `references/tkinter-node-link-graph.md` for a concrete, reusable recipe using `tk.Canvas`.

## Verification

After the user selects an option:

- [ ] Implemented only the selected option.
- [ ] Removed or avoided leftover artifacts from rejected options.
- [ ] Compiled and tested the implementation.
- [ ] Inspected the actual rendered artifact (window, page, image).
- [ ] Reported the outcome concisely.
