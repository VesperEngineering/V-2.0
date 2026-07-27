# Present UI Choices Before Implementing

When a user asks for a new visualization, layout, or UI element, do not jump
straight to Tkinter code. Present a short menu of design choices, explain the
tradeoff in one line each, and ask which direction they want.

## The correction to remember

User feedback: *"I meant more informative not 4 boxes. Also i didnt say to
implement anything, i meant choices presented to me for review."*

The pattern:
1. User describes a problem or shows inspiration.
2. Agent offers 3-5 design options with concise pros/cons.
3. User picks a direction.
4. Agent implements.

## Choice template for training-progress displays

| Option | What it is | Pros | Cons |
|--------|-----------|------|------|
| **Metrics inside nodes** | Keep the stage graph; embed live numbers inside each node. | Compact, glanceable, preserves structure. | Text can crowd small nodes. |
| **Stage banner + metrics strip** | Stages as visual indicators; separate strip for numbers. | Clean separation, easy to extend. | Uses more vertical space. |
| **Live event log stream** | Scrolling timestamped log of recent events. | Maximum information density. | Less visual structure. |
| **Expandable dashboard card** | Header + progress bar + collapsible sections. | Most informative, scales well. | More complex UI. |
| **Graph/node-link view** | Obsidian-style nodes and edges that light up over time. | Visually shows growth and relationships. | Slightly more Canvas code. |

## How to present it

Keep the proposal to a few short paragraphs plus a table. End with a direct
question:

> "Which direction do you want?"

If the user shows an example image, name the pattern they are pointing at
(e.g., "Obsidian-style node graph") and confirm before building.

## When it is okay to implement immediately

- The user already approved a specific direction in a previous message.
- The user says "Yes please" or "do it" after seeing choices.
- The change is a one-line fix (color, label, size) with no design ambiguity.

## Anti-pattern

Implementing a 4-box node diagram, then hearing "I meant more informative
not 4 boxes." Present choices first.
