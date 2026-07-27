# Read-Only Git Reconciliation Audit

Use this when canonical Vesper is dirty, local/default history diverges from its remote, multiple branches/worktrees contain retries or residue, and the requested deliverable is an exact safe integration sequence rather than cleanup itself.

This is a **read-only decision pass**. Do not fetch, switch, reset, stash, stage, commit, remove worktrees, prune refs, or alter the canonical checkout while building the fact base.

## 1. Establish policy and audit posture

1. Read the repository governance and current recovery plan first.
2. Set `GIT_OPTIONAL_LOCKS=0` for Git inspection commands to avoid optional index/ref refresh writes.
3. Record the exact audit time and repo path.
4. Treat any branch/ref movement observed during the audit as a concurrent-writer signal. Continue read-only, but re-snapshot before reporting.

## 2. Prove the remote/base identity without fetching

A fetch updates remote-tracking refs and is not read-only. Instead compare the cached ref with the live server:

```bash
GIT_OPTIONAL_LOCKS=0 git -C D:/vesper rev-parse origin/vesper
GIT_OPTIONAL_LOCKS=0 git -C D:/vesper ls-remote --heads origin vesper
```

If they match, the cached `origin/vesper` is a live-proven clean-base candidate. Then record:

```bash
git -C D:/vesper rev-parse HEAD
git -C D:/vesper symbolic-ref --short HEAD
git -C D:/vesper merge-base vesper origin/vesper
git -C D:/vesper rev-list --left-right --count vesper...origin/vesper
```

Use the current remote tip as the integration base when its remote-only commits are legitimate and already accepted. The historical merge base is an ancestry fact, not automatically the safest new branch base.

## 3. Capture canonical dirt without normalizing it

Record separately:

- tracked unstaged names and binary diff digest;
- staged names and binary diff digest;
- complete untracked-file count and grouped inventory;
- durable-looking untracked plans, receipts, ledgers, docs, and lockfiles;
- generated/temp counts.

```bash
git -C D:/vesper diff --name-status
git -C D:/vesper diff --cached --name-status
git -C D:/vesper diff --binary | sha256sum
git -C D:/vesper diff --cached --binary | sha256sum
git -C D:/vesper ls-files --others --exclude-standard -z
```

`git status --untracked-files=normal` collapses directories: its `??` entry count is not the number of untracked files. Report both collapsed entries and the complete `ls-files --others` count.

For a reportedly intentional deletion, check both current index state and deletion history. A file absent because an earlier commit deleted it is not current dirt and must not be restored.

## 4. Audit branches by ancestry and patch identity

For every local and remote-tracking branch, record tip, merge base, ahead/behind, ancestry, and patch-equivalence:

```bash
git -C D:/vesper merge-base --is-ancestor <branch> origin/vesper
git -C D:/vesper rev-list --left-right --count origin/vesper...<branch>
git -C D:/vesper cherry -v origin/vesper <branch>
```

Classification rules:

- **integrated** — tip is an ancestor of the base;
- **superseded** — not an ancestor, but every branch-side patch is equivalent or a newer accepted tree contains the same semantic result;
- **candidate** — has legitimate unique commits or frozen uncommitted work requiring review;
- **ambiguous** — ownership, source truth, or safety meaning cannot be resolved from Git evidence;
- **retain-for-evidence** — recovery refs, stashes, ledgers, reports, or large retired investments that should remain reachable even when not integrable.

When `git cherry` reports `-`, map the patch to its accepted commit with stable patch IDs. For same-path alternatives, compare final blobs/trees as well as patch IDs. Patch IDs can differ when equivalent semantic edits were made on different document bases.

Merge commits can make `git cherry` output misleading because ancestry and patch comparison use a different merge base. Verify merge candidates with parent lists, tree comparison, and explicit per-commit patch IDs before deciding that history is unique.

## 5. Classify branch tips and worktree residue separately

A branch can be integrated while its attached worktree contains valuable uncommitted work. Parse `git worktree list --porcelain` in Python or strip carriage returns explicitly on Windows/MSYS, then run status in each exact worktree path.

For every worktree, record:

- path, branch/detached state, and HEAD;
- tracked staged/unstaged counts;
- untracked entries and durable evidence;
- staged and unstaged binary-diff digests;
- hashes for untracked candidate files.

Never classify a dirty worktree solely from its branch tip. Example: `branch integrated` plus `14 staged/unstaged proposal files` means **integrated branch / candidate worktree**, not safe-to-prune.

## 6. Predict conflicts without writing

### Committed cherry-pick conflict

To model applying commit `<pick>` onto `<target>`, use the picked commit's parent as the synthetic merge base:

```bash
git -C D:/vesper merge-tree <pick-parent> <target> <pick>
```

This identifies exact conflict files and renders conflict hunks without creating an index or commit.

### Uncommitted candidate applicability

Pipe an uncommitted patch into the clean candidate with `git apply --check`:

```bash
git -C <source-worktree> diff --binary \
  | git -C <clean-candidate-worktree> apply --check -
```

Run path-scoped checks too. A full patch may fail because one authority document is stale while independent source/test paths apply cleanly.

Build a changed-path intersection matrix across:

- remote-only commits;
- local unique commits;
- canonical tracked dirt;
- each dirty candidate worktree;
- large unique branches.

Distinguish **textual conflict** from **semantic conflict**. An additive 230-commit-old branch may have no path overlap but still depend on retired contracts and remain unsuitable for the current milestone.

## 7. Derive the integration sequence

1. Start from the live-proven remote tip in a clean integration worktree.
2. Skip commits already present by patch identity.
3. Cherry-pick only unique legitimate commits.
4. Resolve authority/status files semantically; never choose wholesale `ours` or `theirs`.
5. Prefer a linear resolved candidate over a merge that preserves duplicate patch-equivalent history.
6. Keep each independently owned canonical-dirt cluster in a separate commit.
7. Do not claim an exact cherry-pick SHA for uncommitted work. Bind it by source worktree, HEAD, allowlisted paths, and binary-diff SHA-256; create and review its commit later.
8. If two unfrozen status candidates overlap, combine them only after deriving current fields from named receipts. Do not stack both raw patches merely because each applies independently to the base.
9. Re-run the live remote check and all snapshot identities immediately before the final recommendation.

A useful final sequence distinguishes:

- **committed and reproducible now** — exact SHA chain;
- **cleanly portable but unfrozen** — patch digest and allowlist;
- **manual reconciliation required** — conflict files and source-of-truth rule;
- **parked outside the milestone** — preserved candidates/evidence, not silently discarded.

## 8. Report format

Lead with:

1. exact clean base and live-remote proof;
2. preferred commit sequence and whether a merge is needed;
3. whether canonical stayed untouched;
4. which milestone requirements remain incomplete.

Then provide:

- local/remote divergence and duplicate mapping;
- canonical dirt disposition by path cluster;
- complete branch classification;
- complete worktree classification;
- exact conflict files and `apply --check` results;
- patch/tree/diff identities;
- validation performed and explicitly not performed.

If concurrent agents advanced refs during the pass, name the final snapshot time and mark any moving candidate **unfrozen**. Do not present an intermediate SHA as final.

## Pitfalls

- **Fetching during a read-only audit:** use `ls-remote`; fetch mutates tracking refs.
- **Branch integrated = worktree disposable:** false; inspect residue independently.
- **Collapsed untracked count = file count:** false; enumerate with `ls-files --others`.
- **Patch-equivalent = identical history:** false; retain exact mapping and choose the cleaner topology.
- **No path overlap = safe integration:** false; old additive branches can be semantically obsolete.
- **Uncommitted work has a cherry-pick SHA:** false; use a patch digest and allowlist.
- **A clean integration branch means the milestone is complete:** false; compare its changed paths to every roadmap exit gate.
- **Candidate commits satisfy repo policy automatically:** inspect required commit bodies, review receipts, and validation evidence before publication.
- **Read-only verification includes running tests by default:** tests often write caches/temp artifacts. Under a strict read-only request, use Git/tree checks and report that behavioral tests were not rerun.
