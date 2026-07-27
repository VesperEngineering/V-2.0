# Standing `/goal` + Kanban split-brain preflight (2026-07-21)

Use this reference when a standing Hermes goal mirrors itself into a Vesper Kanban goal.

## Live incident pattern

A standing goal in session `20260721_092330_03e103` created Kanban root `t_d6e5a7b1` with:

- title `Vesper Milestone C — First Viable Model`;
- key `vesper-milestone-c-first-viable-model-v1`;
- `goal_mode=true`, `goal_max_turns=60`;
- `assignee=null` at create time;
- clean isolated worktree `D:/vesper-worktrees/milestone-c-first-viable-model`.

The coordinator comment claimed the unassigned card could not dispatch. Global `kanban.default_assignee=vesper-clarke` then assigned it, spawned run 428, and blocked it after the Clarke profile exhausted its separate `agent.max_turns=15`. At the same time, SessionDB still held the standing `/goal` as `active`, `0/60`. This proved that standing-goal state and Kanban goal-mode state were not coupled and created two potential coordinators against one worktree.

## Dependency deadlock pattern

The worker produced:

```text
root t_d6e5a7b1 -> implementation t_c0b35c19
implementation -> verification t_35114881
implementation + verification -> independent review t_6ee24e05
review -> governance t_55bdb932 + briefing t_78c1c628
```

Because a Kanban child waits until every parent is done, the blocked root prevented implementation from becoming ready while the root itself awaited its descendants.

Duplicate-safe repair order (future CLI mutations, never direct SQL):

```text
unlink root -> implementation
link governance -> root
link briefing -> root
unblock root        # open parents route it to todo
promote implementation
```

This turns the root into the final aggregator. Always re-read immediately before applying because a standing goal may still be mutating the board.

## Card registry rule

- Reuse the existing root and child IDs; do not recreate children merely because they lack idempotency keys.
- Before any new `create`, search all terminal and archived tasks by exact key, normalized title, contract/source hash, creator, and parent set. CLI create-time dedup covers only non-archived matching keys.
- Give every genuinely new control/review/experiment card a creation-time key. For experiments, derive it from immutable objective + data-manifest + evaluator + candidate-spec hashes, not a display title.
- Do not use `assignee=None`, `blocked`, or `triage` as a singleton or human gate without checking live dispatcher/default-assignee/auto-decompose behavior.

## Verification read-back

Capture one coherent `mode=ro` transaction over tasks, links, comments, events, and runs. Also read `state.db/state_meta[goal:<session>]`, global Kanban config, assignee profile `agent.max_turns`, and the exact worktree branch/HEAD/status. The key invariant is one active writer, one acyclic dependency graph, and one canonical card lineage.