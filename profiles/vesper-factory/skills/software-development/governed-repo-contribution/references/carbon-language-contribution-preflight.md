# Carbon Language contribution preflight

Use this reference when helping a newcomer contribute to `carbon-language/carbon-lang`.

## Repository and policy

- Work from the contributor's fork as `origin`; add `https://github.com/carbon-language/carbon-lang.git` as `upstream`.
- Default branch is `trunk`.
- Clone with LF preservation (`git -c core.autocrlf=false clone ...`), especially when Windows and WSL coexist.
- Read `AGENTS.md`, `CONTRIBUTING.md`, `docs/project/contribution_tools.md`, and `docs/project/pull_request_workflow.md` before editing.
- Carbon permits AI assistance, but materially AI-derived work should be disclosed proportionally in the commit/PR, typically with an `Assisted-by:` trailer and a short explanation.
- The contributor must satisfy Google's CLA before submitting original code or substantive discussion.
- Always use Bazelisk, never bare Bazel. If `bazelisk` is unavailable, use `./scripts/run_bazelisk.py`.
- Run focused relevant tests and `prek`; Carbon expects small, incremental, review-optimized PRs.

## Selecting a first issue

Treat `good first issue` as a candidate set, not an invitation to start immediately.

For every candidate:

1. Read the full issue body and all recent comments.
2. Check assignees, but do not rely on assignment alone; Carbon often leaves newcomer issues unassigned.
3. Inspect linked closing PRs.
4. Search open PR bodies for the issue number because a PR may not be linked as a closing reference.
5. Exclude work with an active PR, an issue author announcing an imminent PR, or a contributor recently reporting active work.
6. Assess whether the label is aspirational: compiler issues crossing parsing, SemIR, checking, lowering, or unsettled language representation may still be poor first tasks.
7. If no clean issue remains, do not race contributors or force a complex task. Establish the build environment and ask `#contributing-help` for a small current task.

Useful checks:

```sh
gh issue list --repo carbon-language/carbon-lang \
  --state open --label "good first issue"

gh issue view ISSUE --repo carbon-language/carbon-lang \
  --json number,title,body,comments,assignees,labels,closedByPullRequestsReferences

gh search prs --repo carbon-language/carbon-lang \
  --state open --match body "ISSUE"
```

## Windows/WSL setup principle

Carbon's documented development environments are Debian/Ubuntu and macOS. On Windows, prefer WSL2 Ubuntu and keep the build checkout in WSL's native Linux filesystem rather than under `/mnt/c`; this avoids cross-filesystem performance and line-ending problems.

Before installing anything, inspect the WSL distribution, current default Linux user, available disk, and toolchain. If the distribution launches as `root` and has no regular user, pause for explicit approval before creating/configuring a user; do not silently normalize account or sudo policy. After user setup, clone a fresh LF-preserving checkout inside the Linux home directory and establish one known-good baseline test before selecting implementation work.

## Local notes without polluting the PR

A newcomer may want a notebook inside the checkout. Create a clearly local file such as `LOCAL_CONTRIBUTION_NOTES.md` and add it to `.git/info/exclude`, not the tracked `.gitignore`. Verify with both `git status --short` and `git check-ignore -v`. This keeps personal notes available without changing project files.