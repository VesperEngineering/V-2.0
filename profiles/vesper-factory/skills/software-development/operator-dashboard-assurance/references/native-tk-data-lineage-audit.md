# Native Tk data-lineage and live-source audit

Use this reference for Tkinter/native operator consoles whose values come from files, SQLite, process telemetry, provider ledgers, or multiple asynchronous refresh payloads.

## 1. Freeze source and identify the loaded runtime

1. Capture `HEAD`, branch, porcelain status, tracked-diff hash, staged-diff hash, and source mtimes before inspection.
2. Read the desktop shortcut target, arguments, working directory, and icon. Do not assume a documented launcher is the one operators use.
3. Inspect the process tree and visible native window PID/title. A virtual-environment launcher or shim may spawn the real interpreter; parent plus child is often one logical runtime, not two competing windows.
4. Compare process start time with relevant source mtimes. Native Python processes retain imported code after files change.
5. Recheck source hashes during and after the audit. For a current-state audit, re-trace files that moved and distinguish **runtime-loaded source** from **final worktree source**. For an immutable-candidate review, any movement invalidates the review as defined by the stricter review contract.

## 2. Build the display-value map from the final writer

For every visible value, trace:

`authoritative artifact/API -> loader query/parser -> normalized model field -> renderer/StringVar -> final displayed text`

Inventory static labels and every write to each mutable UI variable. Multiple refresh handlers can write the same `StringVar`; source order is not enough—queue ordering determines the value the operator finally sees. Record both intermediate and final scope.

Create an explicit state-vocabulary matrix. Common defects include:

- loader emits `green` while counters count only `pass`;
- loader emits `missing_source` while counters count only `missing`;
- renderer defaults an unknown Kanban state to green;
- cards use one normalization helper while counters use raw strings.

Run a pure probe against the live loader output to print exact labels, counters, selected blocker fields, and color buckets. A passing widget-cache test does not validate semantic state mapping.

## 3. Separate every clock and freshness field

Keep these distinct:

- UI apply/sync time;
- payload observation time;
- provider observation time;
- receipt filename date;
- receipt file mtime;
- artifact-internal source session/date;
- authoritative database maximum normalized timestamp;
- age and SLA decision.

A field labeled `FRESHNESS` must not merely echo a filename date or blank model timestamp. A five-second UI sync does not make an old artifact fresh.

When governance Markdown repeats historical and canonical values, test the exact parser. A first-match regex can consume an obsolete field even when a later canonical summary supersedes it.

### Mixed SQLite timestamps

Do not trust raw `MAX(timestamp)` when a SQLite column mixes integer/real epochs, numeric text, and ISO text; SQLite type ordering can select an older textual value. In `mode=ro`:

1. inspect `typeof(timestamp)` counts and per-type min/max;
2. use the repository's shared normalization contract where available;
3. otherwise normalize epoch seconds/milliseconds and ISO timestamps before comparing maxima;
4. compare the result with the receipt and displayed date.

## 4. Challenge artifact admission, not just existence

A non-empty CSV is inventory, not proof of a current admitted candidate. Require binding to:

- authorized task/run identity;
- successful producer receipt;
- source session and decision date;
- exact input/output paths and before/after sentinels;
- structural/domain validator result;
- independent review state when governance requires it.

Cross-check the task database and latest comments/events. A blocked task plus later unbound `SUCCESS` artifacts must not render green merely because a file exists.

When an aggregator selects the “worst” row, inspect equal-state ties. Stable list order can select an older source and hide a newer contradictory source even though both normalize to green.

## 5. Verify native Kanban projections directly

Open the board SQLite database with URI `mode=ro` and compare loader output to direct SQL for:

- task count, ordering, statuses, assignees, titles, and IDs;
- comments and event ordering;
- latest run summary/result;
- created/started/completed timestamps;
- worker-log path, mtime, byte length, and whether the UI displays a tail or an old prefix.

Then inspect renderer transformations separately. Flag rewritten task identifiers, omitted timestamps, task-count-derived “worker status,” silent empty fallbacks, and slicing that turns newest-first rows into older events.

Treat enabled `APPROVE`, `REJECT`, `UNBLOCK`, or comment controls as mutation authority even if the title or module says `Read Only`. Trace identity, attribution, command boundary, result handling, and audit receipt. Never click these controls during a read-only audit.

## 6. Preserve provider scope and stale inheritance

Keep OpenAI workspace/session counters, provider quota, OpenRouter account/key/credit activity, and local request receipts separate. Verify that compact appbar formatting does not strip scope, observation time, or `STALE` from an otherwise correctly typed snapshot.

For a strict read-only audit, avoid invoking management loaders that persist caches. Read an existing sanitized cache and local ledger, or inject a read-only fixture into the formatter. State when this reproduces formatting rather than performing a fresh account call.

## 7. Minimum report evidence

Include:

- exact runtime shortcut/process/window identity;
- exact current displayed labels and final counter scope;
- a lineage table for each major widget;
- direct SQL/file/provider cross-checks without secret values;
- path:line findings for parser, normalization, aggregation, renderer, and control wiring;
- source movement observed during the audit;
- tests/probes run and whether they exercised runtime-loaded or final source;
- an explicit statement that no source, board, database, task, or credential was modified.

## 8. Prove poll recovery, not only the happy path

A trustworthy Tk poll loop has four observable invariants:

1. only one fetch per source is in flight;
2. every worker completion reaches the Tk queue, including exceptions;
3. the Tk handler clears the in-flight flag and schedules another attempt;
4. last-good values survive errors with a visible stale/error marker.

Use a finite failure-injection probe: wrap the real loader so call 1 raises and call 2 delegates to the real implementation, start the actual Tk event loop, and wait for the retry **plus the loader's real duration**. Assert at least two calls, a non-`None` recovered snapshot, repeated independent polls, and an empty `report_callback_exception` list. A seven-second harness is insufficient when the retry delay is five seconds and the successful aggregation itself takes six seconds; measure the whole path rather than assuming timer delay equals refresh cadence.

For fast SQLite panels, instrument the real read helper and count calls during a bounded event loop. This proves the advertised subsecond cadence and catches implementations whose comments claim 500 ms while data is only refreshed by a separate five-second snapshot.

## 9. Finite native interaction harness

Create the real `Tk` root and application, replace `root.report_callback_exception` with a collector, and schedule deterministic actions with `root.after` only after the initial snapshot has had time to load. Capture at least:

- evidence state, authority, session, provider formatting, and normalized pass/fail/waiting counts;
- source/receipt/detail tab content lengths;
- repeated evidence ↔ Kanban view toggles;
- worker/card counts, selected task identity, detail title, summary, and log content;
- manual log scrolling disables auto-follow and FOLLOW restores it;
- recursive visible-widget count by `winfo_class`, including a required zero when visible scrollbars are forbidden;
- final view, window title/version, in-flight flags, and callback-error list.

Do not call Tk widget methods from worker threads. Queue `(kind, payload, captured_identity)` and discard stale detail when the captured task ID no longer matches selection. When mouse-wheel-only scrolling is required, bind wheel handling to child labels/frames as well as the canvas; Tk events do not reliably bubble to the parent widget binding. Return `"break"` on `Text` handlers to suppress the class binding and avoid double scroll.

## 10. Isolated mutation and launcher closure

For audited Kanban controls, mock `subprocess.run` first and assert executable, board, subcommand, arguments, timeout, no-shell behavior, and Windows no-console flags. Then set `HERMES_HOME` to a temporary directory, create a disposable board with the real Hermes CLI, run `create → comment → unblock → block → unblock → complete`, and query that temporary `kanban.db` for final status/result and event kinds. Remove the directory in `finally`. Compare production-board counts before and after when an extra non-mutation assurance is warranted.

Treat source runtime and desktop deployment as separate gates. A direct interpreter launch can prove callbacks and data but not shortcut correctness. After the last code change, launch the actual `.lnk`, read back target/arguments/working directory/icon through the Windows shell API, map visible window to process command line, confirm the intended semantic version, and check for console/duplicate processes. If a tool limit interrupts full-suite or shortcut closure, report the exact last-green focused tests and keep the verdict qualified rather than claiming release certification.
