# Git Publication State

Use this vocabulary in governed-worktree reports.

| State | Meaning | Required report field |
| --- | --- | --- |
| Committed | SHA exists locally | commit SHA and parent |
| Published | SHA is reachable from a remote branch | remote branch/ref |
| PR opened | A GitHub pull request was actually created | PR URL/number |
| Integrated | Default branch contains the commit or its cherry-pick | default-branch SHA |

A Git host may print a “create pull request” URL after a new branch push. That is a suggestion, not proof that a PR exists.

## Default-branch integration

When the candidate base predates the remote default branch, do not describe a branch publish as an integration. Use a clean integration worktree, apply the candidate to current remote default, resolve only evidence-backed conflicts, run the candidate’s required checks, then push default. Report both source and resulting integration SHA because a cherry-pick normally creates a new SHA.
