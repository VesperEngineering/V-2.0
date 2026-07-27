# Read-Only Isolated No-FF Merge Audit

Use this recipe when an exact candidate commit has already been integrated in an isolated worktree, canonical has substantial unrelated tracked/untracked work, and the reviewer must return only `PASS` or `HOLD` without changing the repository, evidence, board, profiles, schedules, or runtime state.

## Authority boundary

- Treat the audit as strict read-only. Do not create worktrees, merge simulations, refs, commits, caches, receipts, pytest scratch, or temporary files unless the user separately authorizes them.
- When the user explicitly permits **external scratch** and requests fresh gates, use one uniquely named, same-drive scratch root outside the repository/evidence roots. Prefer an external local Git clone checked out detached at exact merge `M` over `git archive`: focused tests may call `git rev-parse HEAD`, so an archive-only run can produce a setup-only failure despite valid source. A safe transient pattern is `git clone --shared --no-checkout <repo> <scratch>/src` followed by `git -C <scratch>/src checkout --detach <M>`. Route pytest `--basetemp`, `PYTHONPYCACHEPREFIX`, logs, and generated artifacts into that owned scratch root; verify the clone's exact HEAD before testing and remove only that owned root afterward.
- Set `GIT_OPTIONAL_LOCKS=0` for Git reads so status/diff inspection does not opportunistically refresh the index. Set `PYTHONDONTWRITEBYTECODE=1` for Python probes.
- Do not use `git merge-tree --write-tree`, `git worktree add`, `git update-index`, or a real merge during the audit.
- `PASS` may authorize only the exact local no-ff merge named by the user, followed by immediate preservation verification. It does not authorize push, deploy, release, scheduler/provider/model changes, broker/order access, or operational/trading action.

## 1. Bind identity and topology

For base `B`, candidate `C`, and isolated merge `M`, prove:

1. all three objects exist and are commits;
2. canonical is on the expected branch at exact `B`;
3. the frozen topology is one of these two safe classes:
   - **Exact-base descendant:** `merge-base(B,C) == B` and `B` is an ancestor of `C`; or
   - **Explicitly bound tree-neutral sibling:** the prompt or frozen evidence explicitly expects a divergent merge; `X = merge-base(B,C)`; `C` has exactly one parent and it is `X`; `B^{tree} == X^{tree}`; and `git diff --quiet X B --` succeeds. This exception is for an ancestry-only/no-content canonical merge followed by an exact candidate from the tree-identical parent—not for arbitrary divergent branches.
4. `M` has exactly two parents in order: first `B`, second `C`;
5. `C` is an ancestor of `M`;
6. `C^{tree} == M^{tree}` and `git diff --quiet C M --` succeeds;
7. the named integration ref and worktree still point to `M`.

Tree equality alone is insufficient: a merge with unexpected parents can preserve the same tree while authorizing the wrong history. For the tree-neutral sibling class, also require `B..C` and `B..M` to have the same allowlisted path set and byte-identical binary diff. If the divergent topology was inferred rather than explicitly bound, if `B` changed content relative to `X`, if `C` has another parent, or if any diff identity differs, return `HOLD`.

Before the first check, write an in-memory **binding inventory** that separates:

- authoritative bindings explicitly supplied by the user or frozen evidence (`B`, `C`, `M`, named integration ref/worktree, named source/review worktree, expected manifests/logs);
- ancillary observations discovered during inspection (other branches or worktrees that happen to point at `C`).

Do not silently promote an inferred branch name into a PASS/HOLD invariant. If an ancillary source branch advances to a clean descendant while exact `C` remains immutable, `M` retains ordered parents/tree identity, the named integration ref/worktree remains at `M`, and at least one evidence-named exact-`C` source/review worktree remains clean, report the advance as informational rather than a material blocker. If the moving ref/worktree was explicitly bound by the prompt or evidence, or no exact-`C` evidence worktree remains, treat the drift as material and return `HOLD`.

## 2. Recompute exact candidate scope

- Parse `git diff --name-status -z B C --` and `git diff --name-only -z B C --`; require the expected logical-entry count, unique-path count, statuses, and allowlist.
- Recompute the same lists for `B..M`; require exact equality with `B..C`.
- Hash raw `git diff --binary B C --` bytes with SHA-256 and compare the digest to the frozen review binding. Require the `B..M` binary diff to be byte-identical.
- Run read-only `git diff --check B C --`.
- Record additions separately from modifications/deletions because additions need stronger collision checks.

## 3. Prove canonical dirt is untouched and non-colliding

Parse `git status --porcelain=v1 -z --untracked-files=all` correctly, including the extra NUL path carried by rename/copy records. Check all of the following:

- exact status-entry count;
- exact ordered `(status, path)` rows against the frozen status evidence;
- exact rows against the content manifest;
- no staged or unmerged index entries unless explicitly expected;
- no exact candidate/status intersection;
- no case-folded intersection on case-insensitive filesystems;
- no ancestor/descendant path-prefix collision in either exact or case-folded path space;
- no candidate-added target that already exists in the filesystem;
- no candidate-added path below a non-directory, symlink, junction, or reparse-point parent unless the frozen contract explicitly allows it and containment is independently proven;
- no candidate-added collision with either ordinary untracked paths or ignored paths, including exact, case-folded, and prefix forms.

Do not stop at path counts. Independently verify every manifest entry:

- stream-hash regular files, compare byte size and SHA-256;
- inspect symlinks/reparse links without following them and compare the exact link target;
- reject duplicate, absolute, or traversal-containing manifest paths;
- require the manifest base SHA and manifest digest to match the frozen audit binding.

A 2,000-entry status list can remain numerically unchanged while one user file changes bytes. Full content verification is what proves preservation.

## 4. Verify isolated worktrees are clean

For both the candidate source and integration worktree, bind HEAD/branch and require:

- zero porcelain status entries, including untracked files;
- empty worktree diff;
- empty cached diff;
- zero unmerged records;
- no merge, cherry-pick, revert, or rebase state marker.

## 5. Authenticate focused, critical, and broad evidence

### Evidence integrity

- Recompute the digest of the evidence manifest when an expected digest exists.
- Recompute every referenced receipt/log digest; do not trust filenames or a top-level `PASS`.
- Confirm every receipt binds exact `B`, `C`, `M`, worktree, path count, and closed authority fields.

### Focused and critical gates

Under a strict no-write audit, do not silently rerun pytest: even cache-disabled tests create basetemp fixtures and may invoke artifact writers. Instead authenticate the existing exact-candidate focused log/receipt and independent-review readback. If fresh read-only probes are useful:

- compile exact changed Python blobs from `git show M:<path>` in memory with Python `compile(...)`; this checks syntax without `.pyc` writes;
- run critical Ruff only with `--no-cache` and `PYTHONDONTWRITEBYTECODE=1`;
- rerun `git diff --check`.

If the decision contract requires a fresh pytest run, obtain explicit scratch-write authority and use a unique external same-drive basetemp; otherwise return `HOLD` rather than violating read-only scope. With that authority:

1. check out exact `M` detached in the external scratch clone and verify `HEAD == M` before testing;
2. set `PYTHONPATH` to that clone and run pytest with `-p no:cacheprovider --basetemp <external>`;
3. run `py_compile` only with `PYTHONPYCACHEPREFIX=<external>` and verify no `.pyc` appeared in the scratch checkout itself;
4. run Ruff with `--no-cache`;
5. recheck the real canonical/integration trees afterward, because a supposedly hermetic test may still contain a hard-coded writer.

If an archive-only first run fails solely because `.git` is absent (for example, a production helper invokes `git rev-parse HEAD`), classify it as a harness/setup result, not a candidate failure. Rerun once from the exact detached scratch clone and report both attempts; do not weaken the test or run it in the protected worktree.

### Broad failure baseline

- Authenticate both baseline and final broad logs by SHA-256.
- Require complete logs with a terminal summary and terminal newline.
- Parse the terminal summary semantically rather than requiring decorative `====` delimiters: pytest may emit a plain final line such as `30 failed, 5048 passed, 76 skipped, 5 warnings in 394.70s (0:06:34)`, and zero-warning baselines may omit the warnings field entirely. Require exactly one valid terminal summary after the short-failure section.
- Parse each `FAILED <nodeid>` row independently, removing only pytest's trailing ` - <message>` description.
- Compare unique counts, exact sets, and order. Equal failure counts are not enough.
- Report added and removed node IDs explicitly.
- Check whether any failed node belongs to a candidate-changed test path.
- Keep the broad suite honestly non-green even when its exact known failure set is unchanged; explain why that unchanged baseline does or does not block the requested integration decision.

### Post-merge canonical broad gate

The isolated merge and the dirty canonical checkout may expose different local evidence. A data-rich canonical checkout can make old baseline failures turn green even when the exact source tree is unchanged. Therefore:

- require exact baseline failure-set equality in the clean isolated integration worktree unless the contract explicitly expects a repair;
- after the approved canonical merge, parse node IDs again and require the canonical failure set to be a **subset** of the authenticated baseline with zero added nodes; report every removed node rather than demanding equal counts;
- never accept a new node merely because the total failure count fell;
- preserve and hash the canonical log separately from the isolated log.

Run potentially long canonical broad suites as tracked background processes with completion notification. A foreground tool timeout is infrastructure state, not a pytest verdict; obtain the process's terminal exit and complete summary before classifying it. After the canonical test run, verify every pre-integration manifest entry again because tests may rewrite ignored or untracked artifacts in the dirty checkout.

## 6. Final concurrent-drift recheck

Immediately before issuing the verdict, re-read at minimum:

- canonical branch and HEAD;
- full status rows and count;
- content-manifest equality;
- candidate/merge parent and tree bindings;
- integration-worktree cleanliness;
- evidence hashes.

Any unexplained drift in an **authoritative binding from the predeclared inventory** converts the decision to `HOLD` even if earlier checks passed. Ancillary ref movement is not automatically material: classify it against the inventory, prove it cannot alter exact `B`/`C`/`M`, the named integration ref/worktree, the preservation set, or authenticated evidence, and report it separately. Never widen or shrink the binding inventory merely to force the desired verdict.

## Implementation hardening

- `git check-ignore --no-index -z --stdin` uses exit code `1` to mean **no supplied path matched an ignore rule**. Treat that as a clean result when stdout is empty; only exit codes greater than `1` are command failures. Feed every candidate-added path plus all of its relative ancestors, and pair this with `git status --ignored=matching --porcelain=v1 -z --untracked-files=normal` so ignored parent directories participate in exact, case-folded, and prefix collision checks without recursively enumerating a large ignored environment.
- A broad-log parser must accept both terminal summary forms: `N failed, P passed, S skipped, W warnings in ...` and `N failed, P passed, S skipped in ...`. Normalize the omitted warning field to zero, require exactly one terminal summary after the short-failure section, and still compare all `FAILED <nodeid>` rows by unique count, exact set, and exact order.
- For fresh external-scratch gates, compile every changed `.py` path with `PYTHONPYCACHEPREFIX` outside the detached clone and then explicitly scan the clone for `.pyc` files. A zero `py_compile` exit is not by itself proof that bytecode stayed outside the checkout.
- Keep the machine-readable audit report and fresh-gate logs inside the owned external scratch root. This allows a one-token verdict contract without sacrificing reproducibility or weakening the internal evidence trail.

## Verdict format

Lead with exactly `PASS` or `HOLD`, then report:

- identity/ancestry and parent order;
- tree and binary-diff identity;
- exact path scope;
- collision result;
- canonical manifest/content result;
- worktree cleanliness;
- focused/critical evidence;
- broad final result versus baseline;
- files changed by the reviewer (normally none);
- precise authority retained.

For `PASS`, restate that only the exact local no-ff merge is authorized and that post-merge verification must prove the unrelated dirty/untracked set and content survived. For `HOLD`, name the smallest failing invariant and do not suggest bypassing it.