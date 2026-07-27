# VOT Agentic Workflow Layout

Use this contract when redesigning VOT around autonomous goal execution rather than a worker roster or evidence dump.

## Information architecture

### Workflow home

The home page answers: **What is the team doing, what changed, and does the operator need to decide anything?**

Use top-level workspace navigation:

- `WORKFLOW`
- `KNOWLEDGE`
- `DECISIONS`
- `HISTORY`
- `SYSTEM`

Do not put the evidence spine, Kanban queue, research queue, provider detail, and worker roster into one persistent left rail. The left side is navigation-only when present; the main canvas carries the operational content.

Represent the current approved objective as a connected card flow:

```text
GOAL -> PLAN -> STAFF -> REVIEW -> DECIDE
```

Below it, show active workflow cards. Each card represents a goal or bounded unit of work—not a person—and should expose:

- state and current phase;
- approved parent objective;
- worker/subagent context;
- child-card or dependency count;
- latest meaningful event;
- expected output or receipt;
- whether operator action is actually required.

Workers and subagents are metadata inside the workflow card. Never turn a dynamic workforce into the primary navigation model.

### Right-side use

Do not reserve a permanent right inspector merely to repeat the selected card.

On the Workflow home, the right region may contain a compact `LEARNED / ACTED` pulse:

- learned conclusion + source/freshness;
- completed action + actor/receipt;
- no implied authority.

When content needs depth, switch to a full-width page instead of squeezing it into a narrow inspector. A temporary inspector remains appropriate for bounded source/receipt detail, but it should earn the space.

### Knowledge & Actions page

The Knowledge page answers: **What did Vesper learn, and what did it actually change?**

Separate these classes visibly:

1. **Learned facts**
   - observation or conclusion;
   - evidence source;
   - freshness/integrity posture;
   - scope and confidence;
   - no side-effect claim.

2. **Action receipts**
   - real completed side effect;
   - actor;
   - timestamp;
   - result;
   - receipt/artifact/commit handle;
   - authority class.

3. **Human decisions**
   - capital/orders;
   - risk/exposure;
   - paid-provider spend;
   - scheduler mutation;
   - production/model promotion;
   - secrets/accounts;
   - unclassified external effects.

Learned information is not proof that action occurred. Action receipts are not standing permission to act again.

## Real-time card contract

Cards may update in near real time, but only from actual task/runtime evidence.

Recommended states:

- `WORKING` — green; current phase and latest verified event;
- `PLANNING` — amber; decomposition/staffing underway;
- `REVIEW` — amber; reviewer and receipt status;
- `IDLE` or `WAITING` — muted gray; explicit wait condition;
- `BLOCKED` — red; blocker and dependency;
- `HUMAN GATE` — blue; exact decision packet awaiting operator authority;
- `COMPLETE` — muted/green; final receipt;
- `UNKNOWN` — fail-closed when runtime evidence is missing, malformed, stale, or contradictory.

Never infer `WORKING` merely because a card is assigned. Require a fresh runtime/task event or receipt.

Data path:

1. Read Kanban SQLite in read-only mode at the established fast cadence.
2. Read local runtime receipts/artifacts without spawning heavy polling subprocesses.
3. Fetch off the Tk main thread.
4. Deliver snapshots through a queue drained by `root.after(...)`.
5. Compute a compact signature per card.
6. Update only cards whose meaningful state changed.
7. Keep `LIVE` static; do not animate timestamps or rebuild unchanged widgets.

A card may list several contextual workers:

```text
Thomas / planning
Riley / implementation
Clarke / review
```

Those labels may open context-only detail, but not worker command surfaces.

## Tkinter mapping

- page stack: `Frame` containers switched by real navigation buttons;
- stage flow: connected `Frame` cards or a `Canvas` with embedded card frames;
- active workflows: scrollable Canvas/frame with mouse-wheel scrolling and no native scrollbar;
- card state accents: 3px left rail + restrained status dot;
- Knowledge/Actions: full-width two-column page;
- detail expansion: replace the body or expand inline rather than defaulting to a permanent right pane;
- refresh: background reader -> `queue.Queue` -> `root.after(...)` -> signature-based targeted update.

## Mockup handling

- Store VOT comparison PNGs in `C:\Users\bgonn\Desktop\VOT LayoutDrafts`.
- Keep deterministic renderer sources under `D:\vesper\.hermes\sketches`.
- Default comparison size is 1920x1080.
- Serialize variants and information consistently: `Layout A`, `Layout B`, …; page/section labels such as `00 / OPERATOR OVERVIEW` through `04 / HUMAN DECISION QUEUE`; and entity labels such as `W-01`, `K-01`, `A-01`, and `D-01`.
- Keep provider capacity visible in every appbar as `OAI <percent>% LEFT` and `OR $<amount> LEFT`. Do not add explanatory captions underneath; use honest `STALE` or `UNAVAILABLE` states when retrieval fails.
- Use actual objective/card titles from data. Do not add generic explanatory slogans such as “Vesper is moving one approved goal.” When no objective exists, render an honest empty state.
- Inspect every board visually for appbar collisions, title/metric overlap, clipped card text, right-edge usage fit, and accidental concentration of information on the left.
- Do not modify production VOT code until the operator selects a direction.

## Visual acceptance checklist

1. The left side is navigation-only or absent; operational data uses the main canvas.
2. Goal flow is understandable within five seconds.
3. Every live card has an evidence-backed state plus a latest event, wait condition, or blocker.
4. Learned conclusions cannot be confused with completed actions.
5. Workers appear as context, not primary navigation.
6. OAI/OR usage is visible without redundant captions.
7. Human-gated decisions are distinct from autonomous work.
8. No filler headline or permanent inspector that repeats selected content.
9. Unknown or stale evidence fails closed as `UNKNOWN`/`UNAVAILABLE`.
10. Serialized labels remain consistent across navigation, sections, cards, and receipts.
