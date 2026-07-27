# Coordinating roadmap goals with parallel audit workers

Use this pattern when one Kanban goal coordinates a milestone while several agents independently audit Git, governance, runtime, or scheduler state.

## 1. Preflight the coordinator profile

Before creating the goal:

```bash
hermes profile show <profile>
hermes kanban --board <board> assignees
```

Verify both the profile's positive `agent.max_turns` and the card's positive `--goal-max-turns`. Treat forced `--skill` values as executable dependencies: confirm those exact skill names resolve in the assignee profile before adding them. An unknown forced skill can terminate the worker before it reads the card.

After the first dispatch, immediately inspect:

```bash
hermes kanban --board <board> show <goal-id>
hermes kanban --board <board> runs <goal-id>
hermes kanban --board <board> log <goal-id>
```

If startup fails before source mutation, comment the exact root cause, verify the worktree is clean, archive the failed card, and create one corrected replacement. Do not blindly replay the same invalid card until its circuit breaker trips.

## 2. Get dependency direction right

In current Hermes Kanban, `create --parent P` means **P is a prerequisite of the new card**. The new card waits while `P` is nonterminal.

Therefore, do **not** create parallel audit cards with the running coordinator goal as their parent when the coordinator needs those audits to finish. That creates a dead dependency: the audits wait for the goal that is waiting for the audits.

Safe shapes:

### Coordinator plus independent audits

- Keep the root coordinator goal running.
- Create audit cards with no task parent.
- Put the coordinator ID and scope in each audit body/comment.
- Give each audit a disjoint read-only or isolated-worktree scope.
- Create a later integration/review card that depends on the completed audits, if a durable dependency join is needed.

### Dependency graph with explicit synthesis

1. Create independent audit cards `A`, `B`, and `C`.
2. Create synthesis/integration card `S` with `--parent A --parent B --parent C`.
3. Keep the high-level milestone card as a tracker/coordinator rather than as a prerequisite of its own evidence producers.

Never rely on title text or comments to change actual dependency semantics; read back parents, children, status, and events.

## 3. Separate audit and edit ownership

- Independent auditors should be read-only unless assigned an explicit isolated worktree and file allowlist.
- One coordinator owns the dependency map and acceptance evidence.
- One integration worktree owns merge/conflict resolution.
- Do not let the coordinator, auditors, and main session edit the same worktree concurrently.
- Review subagent conclusions against source, diffs, commands, and receipts before integration.

## 4. Preserve failure provenance

Archive superseded cards rather than deleting them. Before archival, record:

- failure or dependency-shape cause;
- whether the worktree changed;
- replacement task ID;
- authority boundaries that remained closed.

Terminal reconciliation should close or archive every superseded child so stale descendants cannot later be auto-promoted.

## 5. Windows Git-Bash worktree paths

When calling `git worktree add` through MSYS/Git Bash, pass a native drive path such as `D:/vesper-worktrees/name` rather than an MSYS `/d/...` argument. Git's path conversion can otherwise produce a doubled path such as `D:/d/...`.

Always verify immediately:

```bash
git worktree list --porcelain
git -C 'D:/expected/path' status --short --branch
```

A wrongly located but valid worktree should be preserved until its branch/work is accounted for; do not destructively move or remove it merely for tidiness during active work.

## 6. Completion evidence

The coordinator's final receipt should list:

- root goal and replacement/superseded task IDs;
- audit task IDs and exact scopes;
- worktrees/branches and ownership;
- commits and changed files;
- commands and test results;
- startup/dependency corrections;
- remaining risks and separately denied authority;
- recommended next goal, not automatically launched unless authorized.
