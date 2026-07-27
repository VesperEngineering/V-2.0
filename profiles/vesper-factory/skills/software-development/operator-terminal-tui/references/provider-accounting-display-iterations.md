# Provider accounting display iterations

Use this reference for incremental worker-display passes that extend the existing provider-budget pattern. The budget denominator, stale-value, provenance, and freshness truth rules remain in `references/provider-budget-gauges.md`; this file adds the iteration and token-window lessons.

## One bounded idea per pass

Keep the latest accepted worker-display commit as the comparison baseline. Each pass changes one information-architecture or rendering idea, records a version row in the repository ledger, and compares the candidate on code quality, information accuracy, and real grid readability.

A useful sequence after raw provider values and budget gauges is:

1. Normalize token windows for comparison (Codex session versus OpenRouter today).
2. Add only source-backed deltas or request counts.
3. Preserve the raw provider summaries, scope labels, budget treatment, and freshness row as separate contracts.

Do not silently combine provider account totals, session totals, daily totals, and Vesper receipt attribution into one opaque number.

## Token-window truth contract

- Keep typed numeric fields in the immutable provider snapshot; do not parse display prose to recover numbers.
- Preserve `None`/missing as `unavailable`; never coerce missing provider evidence to zero.
- Label each window explicitly (`session`, `today`, `since launch`) and include request count only when authoritative.
- Label a delta with its source window in the value itself (`+100 launch`), not as a bare signed number; spell out request units (`1187 req`) rather than cryptic suffixes.
- Keep the raw provider summary separately visible so normalization cannot hide source wording, reset semantics, or stale markers.
- Extend the loader and add a loader-propagation assertion when introducing numeric fields; a renderer fixture alone is insufficient.
- Preserve backward compatibility with older test doubles by defaulting optional snapshot fields and using `getattr(..., None)` at the loader boundary.

Compact pattern:

```text
TOKENS / WINDOW
OA session 26.87M +100 launch · OR today 8.26K 1187 req
```

At narrow grids, preserve the labels and values that fit; do not replace them with a false aggregate merely to save rows. Make the provider window explicit on the gauge itself when ambiguity remains (`OPENAI WEEKLY`, `OPENROUTER ACCOUNT [$… left]`); a reset line alone is not a substitute for labeling the capacity window. Probe the actual breakpoint rather than assuming a wide card remains readable. If a new truthful row hides governed selections or footer controls at the minimum supported height, fold the label into an existing heading/row instead of weakening the visibility test or adding a scroll path.

## Verification recipe

1. Add one focused RED test for the new row and one status/model assertion when numeric fields are threaded into the snapshot.
2. Run the literal `pytest` executable with the project virtualenv prepended to `PATH`, external `--basetemp`, and pytest cache disabled.
3. Run the focused provider/layout/controller/hardening/TUI slice.
4. Stage only owned paths, then run `ruff_added_lines.py --cached`, strict `ruff --select E9,F`, compile, and `git diff --cached --check`.
5. Run a fresh pure-render probe at the supported grids (currently `312×63`, `180×50`, and `120×35`), asserting row count, maximum width, footer retention, and visibility of the new row. Text tests are necessary but not visual acceptance.
6. Commit the candidate, test that exact commit in a clean temporary worktree, verify the live remote ref, then bind the exact implementation hash in the ledger with a small documentation commit.

If the user frames the pass as visual/design exploration, defer nonessential tests and lint until the visual direction is accepted or the pass reaches the commit boundary; still run the required pre-commit and fresh verification gates before claiming the artifact is verified.

## Concurrent committed-parent handling

A canonical worktree may contain an unrelated local commit from another lane while the worker-display paths remain clean. Before editing, inspect `git show --stat HEAD` and `git diff --name-only origin/vesper..HEAD`. If the commit is disjoint, preserve it as the parent rather than resetting or cherry-picking over it; record that parent in the candidate ledger row. Push only after verifying the resulting remote fast-forward includes the preserved commit and the new scoped commit. This prevents silently discarding concurrent operations work while keeping the display slice auditable.

## CRLF-sensitive patch recovery

If a targeted patch reports that it changed a test block but removes a neighboring parenthesis, `setattr` opener, or conditional line, stop retrying fuzzy patches. Do not use `replace_all` on repeated structural Python text: a fuzzy match can rewrite multiple unrelated blocks and silently delete surrounding code. Inspect the local region and restore only the damaged file from the current committed baseline:

```text
git show HEAD:tests/path.py
```

Then reapply the intended small edit deterministically, verify `git diff -- path/to/file` contains only that edit, compile the file, and rerun the smallest affected pytest selection before continuing. Do not restore or reset the whole worktree because unrelated operator changes may be present.

If the damaged path was already staged, refresh the index after repair (`git reset HEAD -- path && git add -- path`) before rerunning staged added-line lint. Verify both the working-tree diff and cached diff; a repaired working copy does not repair a stale or corrupted index entry.

## Evidence freshness and ledger hygiene

- Any subsequent code/test edit invalidates the prior pytest evidence, even when the edit is a formatting-only change. Run a fresh literal `pytest` command after the final edit; report the new result, not the previous green run.
- When the repository emits an explicit stale-verification warning, obey it immediately: run the smallest changed-path pytest slice first, then the broader focused slice if the pass is continuing. Do not claim verification from an earlier command.
- Treat the ledger as a separate, low-risk documentation edit. When appending a candidate row, preserve the blank line before `## Candidate review checklist`; inspect the exact tail after patching and run `git diff --cached --check` before committing.
- Keep the implementation candidate and ledger binding as separate commits when the ledger must record the exact implementation hash: verify the candidate commit in a clean temporary worktree, then update the row to that hash, commit the documentation binding, push both, and verify `git ls-remote`.
- Existing governed-selection tests are a hard geometry contract. If a new provider row hides an approval/issue selection or footer at the minimum grid, reduce vertical footprint by folding the truthful label into an existing row/heading; never weaken the visibility assertion or add scrolling merely to accommodate the new metric.
- For scope clarity, use paired capacity labels such as `OPENAI WEEKLY` and `OPENROUTER ACCOUNT`; preserve the provider dollar/percentage values exactly and keep missing account telemetry visibly unavailable.