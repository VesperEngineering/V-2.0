# Governance / Status Truth Reconciliation

Use this reference for an independent, read-only milestone audit spanning governance documents, a live task board, manifests, runtime state, market/data freshness, evidence receipts, and roadmap claims.

## 1. Freeze two baselines

Record both:

- **Source baseline:** repository root, full HEAD, branch/ref decorations, upstream divergence, initial dirty status, and the last commit for every governance document.
- **Observation baseline:** UTC/local time, live task-store query time, process/scheduler query time, and file/database/cache mtimes.

Recheck HEAD/status and live task state before reporting. If another worker mutates the repository during the audit:

- keep committed conclusions bound to the frozen SHA using `git show <sha>:<path>`;
- label uncommitted edits as candidate/in-progress evidence;
- record files that appeared or disappeared during the observation window;
- do not combine baseline line numbers with later working-tree contents.

Strict read-only audits should not run project tests or generators that create caches, basetemps, receipts, or refreshed artifacts. Read existing evidence and pure validators only.

## 2. Model truth as a dependency graph

Recommended order:

```text
authority policy
  -> tracker/board field schema
  -> live Kanban/task provenance + issue registry + lane/process manifests
  -> installed runtime/process/scheduler state
  -> physical databases/caches and market-session expectation
  -> producer receipts -> child validations -> side-effect receipts
  -> fact-base mirror
  -> status/health summaries
  -> roadmap/milestone acceptance claim
```

Downstream mirrors cannot repair upstream ambiguity. Regenerating a health page before the tracker schema, data source, and receipt chain agree only creates a newer contradiction.

## 3. Use two-axis classification

Classify each **claim**, not merely each file.

### Role

- **Canonical:** designated authority for that type of decision or state.
- **Derived:** generated or manually mirrored from upstream evidence.
- **Historical:** valid proof of an earlier run/version, not current authority.

### Condition

- **Current:** agrees with upstream evidence for the stated observation window.
- **Stale:** once valid or policy-canonical but behind current evidence.
- **Missing:** required evidence or field is absent.
- **Contradictory:** two surfaces claim incompatible values for the same semantic field.
- **Unverified:** existence or authority cannot be proven with available access.

Example: a tracker can be `canonical + stale`; a physical cache can be `canonical-for-data-observation + current`; a health page can be `derived + contradictory`.

## 4. Validate schemas before comparing values

Before trusting a consistency validator:

1. Enumerate the tracker’s actual labels and duplicate occurrences.
2. Read the parser’s accepted labels.
3. Verify which duplicate wins (first, last, or section-scoped).
4. Check whether renamed labels return `None` or silently fall back to historical text.
5. Separate parser defects from source-document defects.

A red validator can contain valuable truth while still misclassifying fields because its vocabulary is stale. Report both the real mismatch and the parser mismatch.

## 5. Reconcile live Kanban safely

For a current live SQLite board, use URI read-only mode and one explicit read transaction. Do **not** use `immutable=1` against an actively written WAL database: immutable mode assumes the file cannot change and may ignore uncheckpointed WAL state. If a byte-stable snapshot is required, copy the database together with its `-wal` and `-shm` companions using an approved snapshot mechanism, then query the copy.

Read, at minimum:

- tasks and terminal/nonterminal state;
- parent/dependency links in both directions;
- comments for operator provenance and rejections;
- events for promotion, decomposition, reclaim, complete, and malformed timestamps;
- runs, handoffs, and attachments where present;
- creation/update timestamps and current worker lease/heartbeat evidence.

A card title or `running` status is not enough. Bind milestone state to stable task IDs, dependencies, provenance, and acceptance evidence.

## 6. Reconcile manifests versus runtime

Keep these states separate:

- declared lane/process;
- enabled/configured;
- installed target;
- active process;
- evidence-producing;
- historical fixture/canary.

A lane marked `active` is governance enablement, not process liveness. A source file and passing fixture tests do not prove a resident daemon. Require fresh heartbeat/state/ledger artifacts plus an observed process or installed service/task for runtime claims.

For fact-base mirrors, compute exact set/status differences:

- canonical registry IDs missing from mirror;
- mirror-only ghost IDs;
- shared IDs with status mismatches;
- manifest lanes missing from mirror;
- mirror-only pseudo-lanes;
- registered domains with no current lane.

## 7. Reconcile data and market dates

Resolve the actual consumer path from source before inspecting files. Projects often have multiple similarly named caches.

For OHLCV:

- use the configured benchmark/admitted universe;
- compute per-symbol max dates;
- check gaps, duplicates, and sanity over the relevant window;
- derive the expected latest completed exchange session, including holidays and any EOD grace window.

For macro data:

- inspect the runtime-resolved cache;
- identify the true observation-date column and max date;
- keep observation date, publication date, file mtime, and generation time distinct.

Then compare every consumer: tracker, fact base, freshness receipt, candidate report, pretrade gate, and health summary. A pretrade gate reading stale tracker values while a freshness receipt reads current physical data is a consumer-routing defect, even when it fails closed safely.

## 8. Trace EOD/pretrade evidence end to end

Use this chain:

```text
installed schedule/run
  -> wrapper receipt
  -> selected evidence date/session
  -> freshness child + validation
  -> candidate child + structural validation
  -> pretrade checks
  -> submission receipt
  -> fill/position evidence
  -> reconciliation receipt
  -> status/health summary
```

For each node record status, timestamp, path, producer, source revision, and first failed dependency.

Key semantic rule:

- Wrapper `PASS` can mean the command completed and recorded a safe no-order/fail-closed child result.
- It does **not** imply pretrade readiness, order submission, fill evidence, or operational scheduler success.

A mutable receipt such as `receipts/job-id.json` can be overwritten by a later manual rerun. Correlate it with scheduler last-run time/result and prefer run-scoped immutable receipts for audit history.

## 9. Roadmap acceptance

Treat roadmap files as planning/historical unless they have:

- tracked source identity;
- a canonical task or milestone ID;
- dependency completion evidence;
- acceptance tests/receipts;
- independent review;
- integration commit and current runtime proof where required.

Source implementation can advance beyond an older roadmap while runtime proof remains missing. Describe those as separate facts rather than calling the roadmap simply complete or stale.

## 10. Report shape

Produce:

1. authority hierarchy and observation window;
2. headline milestone verdict;
3. claim-level contradiction matrix;
4. dependency-ordered reconciliation map with canonical source, observed value, classification, upstream dependency, repair, and validation target;
5. explicit safety statement distinguishing fail-closed success from operational readiness;
6. limitations caused by concurrent mutation or unavailable external controls;
7. confirmation that the audit created no repository, board, scheduler, data, or runtime mutations.

## Session-derived pitfalls

- Search tools can return implausible zero matches on Windows drive paths; verify tracked paths with bounded Git enumeration before declaring evidence missing.
- A live worker can delete or rewrite untracked audit artifacts during the same conversation. Re-freeze rather than relying on an early inventory.
- A current-dated health document can already be stale if a later rerun changed child receipts minutes afterward.
- Do not let a generic `PASS` validation of receipt vocabulary obscure a fail-closed child or missing side-effect evidence.
