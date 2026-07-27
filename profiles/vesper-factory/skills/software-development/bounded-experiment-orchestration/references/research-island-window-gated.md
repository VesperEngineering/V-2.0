# Window-gated research island (proven 2026-07-19)

Architecture and scheduling pattern for a GPU research island that feeds a governed kanban, built and proven end-to-end for Vesper.

## Why a window gate, not 24/7 GPU

Continuous GPU research is wrong when the same box is the operator's daytime workstation and runs a market pipeline. Use an asymmetric 24/7 design: monitoring/alerts run around the clock; GPU research runs only in a window.

- Weeknights 18:00–07:00 ET (operator asleep, market closed, machine idle)
- Weekends continuous (hard stop before Monday market prep)
- Market-facing jobs (factor pipeline, briefings, EOD) stay on market hours — running them off-hours just recomputes stale closes at token cost (false-green culture)

Gate with a single pure function `in_research_window(now)` driven by zoneinfo ET boundaries; require tz-aware input and raise on naive datetimes. Test the boundaries (18:00 open, 07:00 close, Fri-night-into-weekend, Mon-early-morning).

## Island skeleton (producer / lease / runner)

Keep the island outside the governed repo (own git repo) so research churn never pollutes production history.

- `research_directions.json` — the ONLY way hypotheses enter the queue. Runners never invent work items.
- `producer.build_manifest()` — idempotent refresh: appends new directions as PENDING with the full contract (id, question, script, primary_metric, stop_rule, budget_seconds, dependencies, artifact_path); never mutates existing items or their status.
- `producer.lease_next()` — atomically flips the first dependency-ready PENDING item to RUNNING. Dependencies are IDs that must be COMPLETE.
- `runner.run_item()` — subprocess under a dedicated venv python with a hard wall-clock `timeout=budget_seconds`; validates the produced artifact against the required schema AFTER exit. Fail-closed: timeout, nonzero exit, missing file, invalid JSON, or missing schema fields all → FAILED, never silent COMPLETE.
- `producer.complete_item()` — terminal status only (COMPLETE/FAILED/BLOCKED); rejects PENDING/RUNNING as terminal states.

## Cron as lease tick (not a second worker)

A 30-min cron tick is a valid leasing worker IF: (a) the run lock prevents overlap, (b) the window gate makes off-window ticks cheap no-ops with honest receipts (`action: outside_window` / `no_pending` — never `no_queue` green noise), (c) each tick runs at most one item. The tick cadence is the polling interval, not the work rate.

## Artifact → kanban bridge

The 13-field candidate schema (hypothesis, economic_rationale, source_commit, dataset_version, backtest_results, walk_forward_results, transaction_cost_assumptions, stability_analysis, drawdown_analysis, correlation_analysis, known_failure_modes, compute_cost, reproducibility_instructions) is enforced twice: runner-side (before COMPLETE) and bridge-side (before card creation). A bridge watch dir on the same filesystem (glob `candidate_factor_*.json` + processed-path ledger) is simpler and more truthful than shelling into WSL to `ls`/`cat`.

## Pitfalls hit during the build

- **pandas 3.0 `groupby(...).apply` excludes the grouping column** from the frame passed to the function — `g["ticker"]` raises KeyError. Prefer plain groupby transforms (`g.pct_change()`, `.rolling().std()` via transform, `.shift()` on the groupby result) over `apply` for per-ticker feature engineering.
- **System Python may lack tzdata** (uv-installed cpython on Windows): `ZoneInfo("America/New_York")` raises `ZoneInfoNotFoundError`. Run island code under the project venv interpreter (which has tzdata), as cron does.
- **Naive `datetime.now()` vs tz-aware gate**: pass `datetime.now().astimezone()` when calling a tz-aware window check, or the gate's naive-input guard fires.
- **First experiment = known-sign smoke test.** Make the island's maiden run a well-documented effect (e.g. 12-1 momentum) precisely because the expected answer is known: IC ≈ 0 or a weak t-stat means the *plumbing* is broken, and a strong t-stat means the loop can count — it is not an alpha discovery. Tag the artifact `scope: research_only_non_production`, and report it to the operator as an infrastructure proof, not a research result.

## Proof shape (what "done" looked like)

queue → lease → bounded run (24s, under 600s budget) → schema-valid artifact → bridge → kanban card with assignee + review chain. Receipt at every hop. 17 tests for window/producer/lease plus ad-hoc verification of live island state.
