# Vesper Governance Model (reference case)

Concrete anatomy of a receipt-chain governed repo, from a full contribution session on `D:\vesper` (2026-07). Use as a map when re-entering this repo or recognizing the pattern elsewhere.

## Policy hierarchy (from loop.md §Policy Hierarchy)

1. `PROJECT_ADVANCEMENT.md` — board; owns current state, next-task selection, execution interpretation, approval boundaries. ~1.1MB / 1579 lines; only header + "Current State" (~first 80 lines) is actionable, rest is append-only "What Is Done" log.
2. `loop.md` — autonomous continuation contract. YAML frontmatter defines `report_only_default` profile: allowed_work, allowed_preview_commands, human_gated_boundaries, stop_conditions, receipt requirements (`write_before_stop: true`).
3. `app/services/lane_manifest.py` — machine-readable lane governance. `LANE_ROWS` tuple of dicts via `_row()` helper; `CORE_AUTHORITY_FLAGS` all default False; `COMMON_FORBIDDEN_ACTIONS`; `LANE_AUTONOMY_PROCESS_MAP` maps lane_id → autonomy process names.
4. `app/services/autonomy_manifest.py` — process inventory (`AUTONOMY_ROWS`): per-process trigger_type, autonomy_state, command_or_producer, safety_gate.
5. `app/services/mcp_capability_manifest.py` — advisory MCP tool guidance only; grants nothing.
6. `AGENTS.md` — short bridge. 7. `SESSION_HANDOFF.md` — resume note (Did/Passed/Next/Remaining), never overrides board.

Conflict rule: board wins for current state; stricter safety boundary wins for authority.

## Human-gated (union across files)

Broker/account/order access; paper-order submission (non-preview); model training/regeneration; model artifact writes; default-checkpoint changes; promotion/registry mutation; scheduler mutation; target/risk mutation; provider/source switching; paid data; secrets/credential values; MCP install/config; private libraries; dependency changes; destructive cleanup; GUI-authority changes; PR/broad git publishing. Only allowlisted autonomous paper command: `python scripts/run_daily_paper_evidence_loop.py --date <YYYYMMDD> --symbol AAPL --side buy --notional 5.00 --no-submit`.

## Task-chain convention

Each research thread: **Plan → Dry Run → Operator Review → Results Review**, each step consuming the prior step's JSON receipt and writing `artifacts/evals/<task_stem>_<date>.md` + `.json`. Task IDs are SCREAMING_SNAKE with trailing date, e.g. `MASSIVE_TOTAL_RETURN_MODEL_SKILL_CONFIRMATION_WINDOW_EXPANSION_RESULTS_REVIEW_20260622`. Board fields `Next ready task` / `Next safe between-closes task` name the current step; each receipt's `next_safe_task` routes to the next.

## Receipt field conventions (JSON sidecar)

- `status` ("PASS"/"FAIL"), `decision` (SCREAMING constant, PASS/FAIL variants), `task_id`, `date`, `generated_at` (ISO UTC), `mode` (e.g. `local_results_review_no_qlib_no_fit_no_training_no_promotion_no_source_switch`)
- `failures`: sorted deduped list; PASS ⇔ empty
- `boundary`: ~16 explicit booleans (external_api_called, model_fit_or_predict_used, broker_account_order_api_used, push_or_pr_publication_used, …) all False except the one describing this receipt type (e.g. `results_review_used: true`)
- `model_admission` / `source_switch`: `{allowed: false, ready/recommended: false, reason}` — always closed in report-only lanes
- `evidence_summary`, `result_interpretation` (incl. `empirical_model_skill_proven: false`, `primary_blocker`), `what_this_proves` / `what_this_does_not_prove`, `recommendation.required_controls`, `upstream_boundary_open_keys`, `next_safe_task`
- Standing constants in this thread: target_basis `total_return_adjusted`, horizon `hold_12`, rank IC floor `0.02`, min confirmation windows `6`, blocker `insufficient_confirmation_windows_for_admission`

## Producer/module layout

- Service module in `app/services/<task_stem>.py`: `DEFAULT_*_RECEIPT_PATH`, decision constants, `build_review(*, root, date_stamp, <receipt>_path)`, `format_markdown(payload)`, `write_receipts(root, payload) -> (md, json)`.
- CLI wrapper in `scripts/generate_<task_stem>.py`: argparse (`--root`, `--date`, `--<receipt>-path`), prints `wrote <paths>` + `<TASK>_STATUS:` / `<TASK>_DECISION:`, exit 0 iff PASS.
- Test in `tests/test_<task_stem>.py`: mock-upstream writer helper, PASS test, fail-closed tests per invariant, `*_static_source_has_no_forbidden_imports` (scans source for alpaca/qlib/sklearn/lightgbm/submit_order), CLI subprocess test.
- NEW (this session): `app/services/research_results_review_framework.py` — `ResultsReviewConfig` dataclass + shared `build_results_review`/`format_markdown`/`write_receipts`; confirmation-window results-review module is the first config-based consumer (receipt-parity verified). Migrate other clones the same way: one at a time, parity-checked, public API preserved.

## Contract-test invariants (test_lane_manifest_contract.py)

- Lane IDs unique AND **sorted alphabetically** (insert new rows in order)
- Every row needs the full REQUIRED_FIELDS set; `maturity_level == "Level 1.5"`; migration_notes must mention `app/services/autonomy_manifest.py`
- All CORE_CLOSED_FLAGS False everywhere; broker_order_capable rows must have requires_operator_approval True
- A test asserts AGENTS.md/loop.md contain the string `python scripts/validate_lane_autonomy_alignment.py --date <YYYYMMDD>` and mention lane_manifest.py — doc edits can break tests.
- Added this session: `local_research_autonomy` lane row formalizing loop.md's standing research autonomy envelope.

## Validation matrix (docs/CODING_STANDARDS.md §Minimum Validation)

- Python change → `python -m py_compile` + focused pytest
- Lane/autonomy surface → focused pytest + `python scripts/validate_lane_autonomy_alignment.py --date <YYYYMMDD>` (writes receipt to artifacts/evals/, STATUS: PASS expected)
- Loop policy → `validate_loop_contract.py` + `run_loop_triage.py`
- Tracker → `validate_quant_ops_tracker_consistency.py`
- Docs-only → `git diff --check`
- Full pytest collection breaks on ~99 files needing pandas/numpy/torch/sklearn (not installed in agent venv) — always run targeted test files.

## Session state notes (2026-07-03)

- Board: Stage 8 accepted-paper observation, 87%, execution `bounded_paper_order_evidence_only`, basket AMD/QQQ/NFLX/COST/CVX.
- Confirmation-window expansion chain completed governance (6/6 windows); `empirical_model_skill_proven` still false everywhere — the whole chain is contract evidence, no fit/predict has ever run (human-gated).
- AGENTS.md GUI-boundary line previously hardcoded `Execution allowed: false` contradicting the board's `true`; rewritten to defer to board without widening.
