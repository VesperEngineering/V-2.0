# Frozen Research Panels and Exact Source Identity

Use this recipe for local CPU research systems that must freeze point-in-time data, derive deterministic features, issue immutable experiment receipts, and reserve one untouched holdout.

## Freeze sequence

1. **Freeze the contract before model comparison.** Bind the universe snapshot, source locations and hashes, target horizon, feature definitions, publication timing, walk-forward windows, costs, portfolio buffers, acceptance gates, model queue, seeds/thread limits, authority denials, and final-holdout dates into one canonical protocol hash.
2. **Materialize a model-neutral panel once.** Resolve membership as of each observation date, prefer adjusted data under a declared recipe, record every source hash, apply only frozen split/alias rules, quarantine unresolved discontinuities, sort deterministically, write in binary mode, fsync, atomically publish, and read back the physical SHA-256.

   **Prove membership effective-date semantics before freezing.** A snapshot key named for a constituent-change date may encode either the pre-change or post-change universe. Classify every matched change-date snapshot by checking whether the added member is present and removed member absent. Then test carry-forward on the change date and following sessions. If all snapshots are pre-change while lookup uses `bisect_right(snapshot_dates, day)`, a change can be delayed until the *next event*, not merely one session. Do not call that point-in-time correctness without an explicit documented effective-time convention and a regression. A confirmed one-event delay invalidates the frozen panel and requires a new generation/hash; it is an integrity HOLD, not a model rejection.
3. **Handle incomplete ingestion dates with a predeclared completeness rule—not a global minimum accident.** A few partially ingested tail dates should not invalidate years of otherwise complete history, and they must never be silently retained as tiny cross-sections. Before any model is run, define the per-date requirement (for example, `required_available = min(frozen_minimum_cross_section, point_in_time_member_count)` plus a frozen coverage ratio), exclude only dates that fail it, and record:
   - every excluded date;
   - coverage before and after filtering;
   - minimum retained cross-section;
   - the rule and threshold in the protocol/manifest.
   Keep this date mask identical for every candidate and the holdout. Never change it after seeing performance.
4. **Materialize deterministic features as a separate immutable artifact.** Bind the panel SHA, protocol SHA, exact feature-builder source hash, feature-column order, row/ticker/date ranges, target-date end, dependency versions, and physical feature-file SHA. Replay must validate bytes and manifest rather than rebuild opportunistically.

   **Treat formatter-only builder drift as real identity drift, not permission to edit history.** If formatting or refactoring changes the builder source hash after materialization, exact replay must fail even when the computed feature bytes would be identical. Preserve the old feature and manifest unchanged; publish a new generation whose filename or generation ID includes the new builder-hash prefix; then rebuild and compare both the new physical feature SHA and logical coverage/schema facts. Identical feature bytes are useful evidence of semantic equivalence, but they do not authorize rewriting the old manifest or rebinding old receipts. Point every runner and verifier at one explicit current generation before supervised work, and rerun the source-bound proof if the builder changes again.

   **Bind the producing dependency stack, not remembered pins.** Record Python and every material numerical/serialization dependency in the feature manifest or a hash-bound runtime lock. Rebuild to a fresh output under a dedicated clean venv. If decoded frames and a canonical logical-table hash match while raw Parquet bytes differ, compare footer metadata (`created_by`, schema metadata, row groups, size) to isolate serializer-version drift. Correct the lock to the version that produced the frozen bytes and require byte-identical reproduction before supervised evidence. Never silently bless a logical match when the contract claims physical SHA reproducibility.
5. **Keep labels chronology-safe.** Feature values at date `t` may use only information available by `t`; the target must point to the exact future session named by the protocol. Training rows must have `target_date <= train_end`. Walk-forward evaluation must exclude all final-holdout observation and target dates.

## Executed-source provenance gate

The preferred path is a local commit of the complete executable slice; no remote push is required.

Before a supervised receipt:

1. Run a status check that includes untracked files, such as `git status --porcelain=v1 --untracked-files=all`. **Do not use `--untracked-files=no` as a source-freeze gate.**
2. Resolve each imported evidence-critical module through `module.__file__` and prove it lies in the intended worktree.
3. Prove each loaded module/config is tracked (`git ls-files --error-unmatch <path>`) and byte-identical to the claimed commit, or reject the run.
4. Bind the local commit SHA, evaluator/feature-builder raw hashes, protocol/data/feature hashes, and exact runtime dependency versions into the receipt.

If dirty-source experiments are intentionally permitted, do not label them only with HEAD. Build a canonical source manifest that includes:

- HEAD SHA;
- raw tracked-diff bytes/hash;
- every untracked executable, test-relevant config, and runner path with raw SHA;
- imported module paths and hashes;
- dependency versions and Python version;
- an explicit `dirty_worktree=true` claim.

Hash that manifest and bind it into every candidate, evaluation, receipt, replay, ledger row, and review packet. A later local repair requires fresh source-bound evidence; old receipts remain historical.

## One-time holdout opening

- Finish the frozen pre-holdout queue first.
- Select the research champion using only walk-forward evidence and frozen gates.
- Require an anchored pre-holdout `KEEP` receipt for a non-baseline candidate.
- Atomically create a single candidate-bound holdout-consumption receipt before or with evaluation.
- Fit only on rows whose targets end before the holdout; evaluate the frozen baseline and chosen candidate under the same costs and buffers.
- Publish `PASS`, `FAIL`, or fail-closed `HOLD` with both evaluation hashes. Never tune, choose another candidate, or modify exclusions after opening the holdout.

## Idempotent receipt-to-Kanban evidence

After the immutable experiment receipt exists:

1. Form a unique marker from `experiment_id` and `receipt_sha256`.
2. Read the supported Kanban API/CLI surface and add a concise comment only when the marker is absent.
3. Read back and require exactly one matching comment.
4. Persist a canonical companion containing board/task identity, marker, receipt hash, comment-body hash, and verification status.
5. Do not advance the queue until the companion exists and verifies. If the comment landed but the local companion write was interrupted, retry by readback rather than posting a duplicate.

## Required regressions

- Every constituent-change snapshot is classified as pre- or post-change, and lookup on the change date plus following sessions proves the declared effective-time convention; changes must not remain delayed until the next unrelated event.
- A partial tail date is excluded under the frozen completeness rule while valid dates remain unchanged.
- Feature materialization replays byte-for-byte and rejects panel, protocol, builder, manifest, or producing-dependency drift. A clean-venv rebuild must reproduce both the canonical logical table and the physical artifact SHA.
- An untracked imported evaluator makes the supervised source gate fail even when HEAD is clean under tracked-only status.
- A module imported from a sibling checkout is rejected.
- Walk-forward output contains no final-holdout dates.
- A non-`KEEP` candidate cannot consume the holdout, and a second candidate cannot reopen it.
- Fault injection after candidate, evaluation, decision, receipt, ledger publication, and Kanban comment resumes without duplicate work or comments.
