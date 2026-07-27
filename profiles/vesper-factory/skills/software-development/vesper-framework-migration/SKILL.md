---
name: vesper-framework-migration
description: "Migrate standalone Vesper results-review services to the config-driven research_results_review_framework, with receipt-parity validation."
version: 1.0.0
author: Hermes Agent
tags: [vesper, migration, framework, receipt-parity, governance]
---

# Vesper Framework Migration

Migrate a standalone `results_review` service in `app/services/` to the config-driven framework at `app/services/research_results_review_framework.py`.

## Building Integrated Signal Pipelines

When extending the Vesper framework with new signal sources (such as factor scores), follow these patterns:

### Handling Pandas MultiIndex for Financial Data
Financial data often comes in panel format with MultiIndex [date, ticker]. To avoid common pitfalls:
- Always verify index structure after slicing: `panel.loc[date]` returns DataFrame indexed by ticker
- When resetting index to get ticker as column: ensure index name is set before reset
- Correct pattern:
  ```python
  slice_df = panel.loc[target_date]  # DataFrame indexed by ticker
  if slice_df.index.name != 'ticker':
      slice_df.index.name = 'ticker'
  slice_df = slice_df.reset_index()  # Now has 'ticker' column
  for _, row in slice_df.iterrows():
      ticker = row['ticker']  # Correct ticker access
  ```
- Incorrect pattern (leads to timestamp confusion):
  ```python
  # WRONG: treats index values (dates) as tickers after reset
  today_df = pd.DataFrame(panel.loc[target_date])
  if 'ticker' not in today_df.columns:
      today_df = today_df.reset_index()
      # If index was date, this creates 'index' column with date values
  ```

### Factor Score Integration Pattern
1. **Data Acquisition**: Load OHLCV and alternative data sources
2. **Factor Calculation**: Compute core factors (volatility, momentum, value, etc.)
3. **Signal Fusion**: Combine factors with alternative data (sentiment, macro, etc.)
4. **Scoring**: Normalize and combine signals into composite scores
5. **Ranking**: Generate ranked lists for portfolio construction
6. **Integration**: Feed scores into existing signal generation workflows

Example integration point in Vesper's no-order report generation:
```python
from app.services.vesper_factor_integration import apply_factor_scores_to_basket
# After obtaining candidate tickers from standard process:
scored_tickers = apply_factor_scores_to_basket(
    candidates=initial_candidates,
    date_str=trade_date.strftime('%Y%m%d'),
    top_k=desired_portfolio_size,
    use_factor_only=False,  # Blend with existing signals
    factor_weight=0.5       # Tune based on backtesting
)
```

### Automated Pipeline Setup
For daily signal generation:
1. Create shell script wrapper (e.g., `vesper_daily_factor_scores.sh`)
2. Schedule via cron (e.g., `0 2 * * *` for 2 AM daily)
3. Ensure proper error handling and logging
4. Validate output before integrating with main workflow

## When to Use

- A `massive_*_results_review.py` file under `app/services/` has 200–400 lines of standalone boilerplate (imports, helpers, `build_review()`, `format_markdown()`, `write_receipts()`)
- The file does NOT import from `research_results_review_framework`
- The script wrapper at `scripts/generate_*_results_review.py` still exists and works

## Migration Recipe (One File at a Time)

All three results-review variants (confirmation_window_expansion, candidate_fit_predict_evaluation, empirical_fit_predict_evaluation) migrated onto the shared framework. Remaining standalone:
- `app/services/massive_total_return_model_skill_candidate_empirical_fit_predict_evaluation_execution_results_review.py` (execution variant, not results-review)
- 47 other non-results-review Massive scripts (plan, dry_run, operator_review types have different validation shapes)

### Step 1 — Read and Understand the Source

Read the full standalone file. Identify these sections:

1. **Constants** — DEFAULT path, READY/PASS/FAIL decision strings, REQUIRED_CONTROLS, RISKY_BOUNDARY_KEYS (will be dropped — framework has its own)
2. **Helper functions** — `_now_iso()`, `_resolve()`, `_relative()`, `_load_json()`, `_section()`, `_closed_boundary()`, `_boundary_open()`, `_missing_controls()` (all will be dropped — framework has them)
3. **`_evidence_summary()`** — maps to `evidence_fields` + `evidence_checks` in the CONFIG
4. **`_primary_blocker()`** — maps to `primary_blocker_fn` in CONFIG
5. **`_result_interpretation()`** — fixed skeleton, framework handles it
6. **`_recommendation()`** — maps to `pass_recommendation` and `fail_recommendation` in CONFIG
7. **`build_review()`** — the main logic: validate upstream receipt, collect failures, build payload. This IS what the framework replaces. Extract the unique validation checks into `_evidence_checks()`.
8. **`format_markdown()`** — maps to `markdown_title` + optional `evidence_lines` callback
9. **`write_receipts()`** — framework handles this identically

### Step 2 — Extract Evidence Fields and Checks

From `_evidence_summary()`, extract:
- `evidence_fields` — tuple of keys extracted from upstream evidence
- `_evidence_checks()` — function that returns `list[str]` of failure codes

From the `build_review()` failure logic, identify which checks are **framework-generic** (decision match, review_ready flag, primary_action match, model_admission closed, source_switch closed, boundary checks, authority flags) vs **task-family-specific** (field-value checks like `protocols_completed != 5`, `empirical_model_skill_proven is not False`, etc.). Only the task-family-specific checks go into `_evidence_checks()`.

### Step 3 — Build the ResultsReviewConfig

Map the source's constants and logic to `ResultsReviewConfig` fields:

| Source constant/logic | CONFIG field |
|---|---|
| `DEFAULT_OPERATOR_REVIEW_RECEIPT_PATH` | `default_source_receipt_path` |
| `READY_DECISION` | `ready_decision` |
| `PASS_DECISION` | `pass_decision` |
| `FAIL_DECISION` | `fail_decision` |
| `REQUIRED_CONTROLS` | `required_controls` |
| evidence field names | `evidence_fields` |
| task-family-specific checks | `evidence_checks` |
| `_primary_blocker` | `primary_blocker_fn` |
| `_recommendation(status="PASS")` | `pass_recommendation` |
| `_recommendation(status="FAIL")` | `fail_recommendation` |
| next_safe_task (PASS branch) | `next_safe_task_pass_template` |
| next_safe_task (FAIL branch) | `next_safe_task_fail_template` |
| model_admission reason | `model_admission_reason` |
| authority list key (`"authority_open_protocol_flags"` etc.) | `authority_list_keys` |
| authority output key | `authority_output_key` |
| markdown title | `markdown_title` |
| output stem | `output_stem_template` |
| what_this_proves list | `what_this_proves` |
| what_this_does_not_prove list | `what_this_does_not_prove` |
| mode_override string | `mode_override` |
| summary_label | `summary_label` |
| `backtick_prose_items` (True for backtick-wrapped prose items) | `backtick_prose_items` |
| `_primary_blocker()` function (dynamically computes blocker) | `primary_blocker_fn` |

**Key invariants:**
- `task_id_template` uses `{date}` format placeholder (e.g. `"..._RESULTS_REVIEW_{date}"`)
- `output_stem_template` uses `{date}` format placeholder
- `default_source_receipt_path` is a Path relative to the repo root (e.g. `Path("artifacts/evals/..._operator_review_20260622.json")`)
- `risky_boundary_keys` → omit (use framework's `RISKY_BOUNDARY_KEYS` default)
- `upstream_evidence_key` → `"evidence"` (framework default)
- `expected_primary_action` → the `primary_action` the upstream operator review must have

### Step 4 — Write the Migrated Service Module

The boilerplate is minimal. Follow the pattern from already-migrated files:

```python
"""Descriptive docstring (report-only)."

Thin config over app/services/research_results_review_framework.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services import research_results_review_framework as framework


DEFAULT_OPERATOR_REVIEW_RECEIPT_PATH = Path(
    "artifacts/evals/<filename_from_original>.json"
)

READY_DECISION = "<original_READY_DECISION>"
PASS_DECISION = "<original_PASS_DECISION>"
FAIL_DECISION = "<original_FAIL_DECISION>"

REQUIRED_CONTROLS = [ ... ]

EVIDENCE_FIELDS = ( ... )


def _evidence_checks(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    # Task-family-specific checks only
    # (framework handles: decision match, review_ready, primary_action,
    #  controls missing, model_admission closed, source_switch closed,
    #  boundary checks, authority flags)
    return failures


# Primary block logic (extracted from original _primary_blocker if present)
def _primary_blocker(evidence: dict[str, Any]) -> str | None:
    ...


CONFIG = framework.ResultsReviewConfig(
    task_id_template=(
        "MASSIVE_..._RESULTS_REVIEW_{date}"
    ),
    ready_decision=READY_DECISION,
    pass_decision=PASS_DECISION,
    fail_decision=FAIL_DECISION,
    default_source_receipt_path=DEFAULT_OPERATOR_REVIEW_RECEIPT_PATH,
    expected_primary_action="...",
    required_controls=tuple(REQUIRED_CONTROLS),
    evidence_fields=EVIDENCE_FIELDS,
    evidence_checks=_evidence_checks,
    markdown_title="...",
    output_stem_template="..._{date}",
    what_this_proves=( ... ),
    what_this_does_not_prove=( ... ),
    pass_recommendation={
        "primary_action": "...",
        "reason": "...",
        "required_controls": [ ... ],
    },
    fail_recommendation={
        "primary_action": "...",
        "reason": "...",
        "required_controls": [ ... ],
    },
    next_safe_task_pass_template="..._{date}",
    next_safe_task_fail_template="..._{date}",
    model_admission_reason="...",
    authority_list_keys=("authority_open_protocol_flags",),
    authority_output_key="authority_open_protocol_flags",
    mode_override="...",
    summary_label="...",
    backtick_prose_items=True,  # if original had backtick-wrapped items
    primary_blocker_fn=_primary_blocker,  # only if original had this
)


def build_review(
    *,
    root: Path | str,
    date_stamp: str,
    operator_review_receipt_path: Path | str = DEFAULT_OPERATOR_REVIEW_RECEIPT_PATH,
) -> dict[str, Any]:
    return framework.build_results_review(
        CONFIG,
        root=root,
        date_stamp=date_stamp,
        source_receipt_path=operator_review_receipt_path,
    )


def _evidence_lines(evidence: dict[str, Any]) -> list[str]:
    return [ ... ]


def format_markdown(payload: dict[str, Any]) -> str:
    return framework.format_markdown(CONFIG, payload, evidence_lines=_evidence_lines)


def write_receipts(root: Path | str, payload: dict[str, Any]) -> tuple[Path, Path]:
    return framework.write_receipts(CONFIG, root, payload, format_markdown(payload))
```

### Step 5 — Verify Receipt Parity

Run both old and new implementations against the **same receipt date** and compare output. The script wrappers in `scripts/` already call the module — so you just need a JSON diff.

```bash
# From repo root (D:/vesper):

# 1. OLD path — git stash or rename the new one temporarily, run old
#    (The old script imports the service module directly)

# 2. Best approach: inline comparison
cd /d/vesper && python -c "
from pathlib import Path
import json

ROOT = Path('.')

# Old implementation
from app.services.massive_total_return_model_skill_candidate_empirical_fit_predict_evaluation_execution_results_review import build_review as old_build

# New implementation (after migration)
from app.services.massive_total_return_model_skill_candidate_empirical_fit_predict_evaluation_execution_results_review import build_review as new_build

# Shell out route: run script with --dry-run before and after
"

# Or run the script with --dry-run:
python scripts/generate_massive_total_return_model_skill_candidate_empirical_fit_predict_evaluation_execution_results_review.py --date 20260622 --dry-run
```

**Receipt parity checklist:**
- [ ] Same `task_id` string
- [ ] Same `status` (PASS/FAIL) for the same input receipt
- [ ] Same `decision` string
- [ ] Same `failures` list
- [ ] Same `mode` string
- [ ] Same `source_receipt` dict
- [ ] Same `evidence_summary` shape
- [ ] Same `result_interpretation` dict (including `primary_blocker`)
- [ ] Same `recommendation` dict (primary_action, reason, required_controls)
- [ ] Same `model_admission` dict
- [ ] Same `source_switch` dict
- [ ] Same `boundary` dict
- [ ] Same `next_safe_task` string
- [ ] Same `what_this_proves` / `what_this_does_not_prove` lists
- [ ] Same `authority_open_protocol_flags` or equivalent key
- [ ] Same `upstream_boundary_open_keys`
- [ ] Format_markdown produces the same output line by line (excluding `generated_at` timestamp)

### Step 6 — Update the Script Wrapper

The `scripts/generate_*_results_review.py` file already calls the service module's `build_review()`, `format_markdown()`, and `write_receipts()` — it should need **no changes** since the public API surface (`build_review(..., root=root, date_stamp=date_stamp, operator_review_receipt_path=...)`) is preserved.

Verify the script still imports and runs after the migration:
```bash
python scripts/generate_massive_total_return_model_skill_candidate_empirical_fit_predict_evaluation_execution_results_review.py --date 20260622 --dry-run
```

## Receipt Parity Reference (Already-Migrated Examples)

| File | Lines (before → after) | Reduction |
|---|---|---|
| `confirmation_window_expansion_results_review.py` | ~280 → 204 | ~27% |
| `candidate_fit_predict_evaluation_results_review.py` | ~300 → 156 | ~48% |
| `empirical_fit_predict_evaluation_results_review.py` | ~300 → 196 | ~35% |
| `candidate_empirical_fit_predict_evaluation_execution_results_review.py` | 381 → ~180 (estimated) | ~53% |

## Pitfalls

- **`evidence_fields` order matters** — must match the original `_evidence_summary()` field extraction order if any consumer depends on key ordering. Use tuples (ordered).
- **`next_safe_task` templates** — must use `{date}` placeholder, not `.format(date_stamp)` in the template itself. The framework calls `.format(date=date_stamp)`.
- **`authority_list_keys`** — different task families use different upstream keys. Check the original `operator_review.get("authority_open_protocol_flags")` vs `operator_review.get("confirmation_window_authority_open_keys")`. The CONFIG `authority_list_keys` and `authority_output_key` must match what the original read and wrote.
- **`_primary_blocker_fn` return type** — must return `str | None`, not the failure code list. The framework expects a single string (or None).
- **`generated_at` differences** — the framework timestamps are ISO UTC, same as the original. Acceptable minor second-level drift. Ignore in diff.
- **Dataclass field ordering is non-negotiable.** `@dataclass(frozen=True)` in Python enforces that all fields with defaults come AFTER fields without defaults. When extending the framework's `ResultsReviewConfig` with new optional fields (e.g., `primary_blocker_fn`, `backtick_prose_items`, `what_this_does_not_prove`), place them at the END of the class definition AFTER `model_admission_reason` (the last required field). Placing a new default-having field between `output_stem_template` and `pass_recommendation` (both required) causes `TypeError: non-default argument 'pass_recommendation' follows default argument` at class-definition time. The correct structure is: all required fields first (task_id_template through model_admission_reason), then all optional/override fields (upstream_evidence_key through primary_blocker_fn). This ordering is invisible in test suites that only import existing modules — it only fails when a new module (or a framework edit) triggers recompilation of the dataclass. Verifying with `py_compile` immediately after any CONFIG field addition catches it.
- **Do NOT delete the script wrapper** in `scripts/` — it's a thin argparse entrypoint that creates the module. It stays as-is since the public API is preserved.