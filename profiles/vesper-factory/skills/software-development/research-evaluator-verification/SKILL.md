---
name: research-evaluator-verification
description: "Extend and verify research-only backtest/evaluator outputs without changing legacy metrics, decision authority, or source data."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [research, backtesting, evaluators, verification, tdd, transaction-costs]
---

# Research Evaluator Verification

## Overview

Use this skill when modifying a research-only strategy evaluator, backtest, or factor study to add reported metrics, benchmarks, transaction-cost treatments, or decision-boundary statements. It is for read-only analysis outputs—not model training, live execution, capital allocation, or compute authorization.

The core rule is **preserve-and-extend**: retain previously published metrics and meanings, then add explicitly named metrics with fully stated methodology.

## Change Contract

Before editing, establish all of the following from the repository:

1. Which return fields are legacy and must remain numerically unchanged.
2. The exact portfolio weighting, rebalance convention, entry/exit timestamps, and cost units.
3. The formation-eligible universe, liquidity screen, and all outcome-time censoring rules.
4. The source-data limitations that the output must not override.
5. Whether the evaluator writes artifacts; do not add files unless the request explicitly calls for them.

State any material ambiguity. Do not silently redefine a legacy field as a new methodology.

## Strict TDD Workflow

Work in vertical slices:

1. **RED:** Add one focused behavioral test for the next output change and run it. Confirm it fails because the behavior is absent, not due to a fixture/import error.
2. **GREEN:** Implement only enough evaluator code to satisfy that test, then rerun it.
3. Repeat for each independent behavior: preserved metrics plus cost-adjusted results, matched control, and explicit outcome boundary.
4. Run the affected test file and then the full suite using the repository-required environment/import configuration.
5. Use a pytest `--basetemp` outside the repository when needed; remove it after the suite.
6. Only after tests pass, execute the real evaluator once against its read-only input. Report observed stdout-derived results; do not create a report file unless requested.

## Return and Turnover Methodology

### Preserve legacy net returns

Keep the legacy return field, formula, keys, and semantics unchanged. Add a separately named field for any new calculation. Tests must assert the legacy result as well as the new result.

### Charge costs per traded side

For a long-only equal-weight target basket, identify all trades rather than charging a blanket round trip per label:

- initial basket entry: one buy side;
- each rebalance: both the sale and purchase sides of the changed notional;
- final liquidation: one sell side.

If turnover is represented as one-way target-weight purchases, later rebalance cost is two times that turnover times the per-side rate. Initial entry and final exit are charged once each. Use a partially overlapping-basket test such as `[A, B]` followed by `[B, C]`; unchanged and full-replacement cases cannot prove this treatment.

State this formula in the evaluator's output methodology, including whether it is a target-weight approximation or an execution simulation.

## Matched Equal-Weight Control

A fair control is built from the same conditions as the selected basket:

1. formation-date feature eligibility;
2. same liquidity screen;
3. same holding-window valid-label/censoring rules;
4. same open/close convention and holding dates.

The control may differ only in selection rule: it equal-weights the complete matched eligible universe rather than the strategy-selected subset. Report matching summaries and windows for the strategy and control so comparisons do not mix different universes or time windows.

## Decision Boundaries

Return an explicit outcome field for research-only evaluators. It must say that the analysis:

- is not approval for paid compute, trading, deployment, or capital allocation; and
- cannot override raw-price, survivorship, data-quality, or outcome-censoring limitations.

This is an output-level guardrail—not a claim that the data limitation has been fixed.

## Phase Authorization Must Survive Direct API Use

A CLI-only gate is insufficient when an evaluator exposes outcome functions as importable Python APIs. Review the direct-call path separately from the command line:

1. Treat every module-addressable authorization class, capability token, sentinel, or global as forgeable by an in-process caller. A leading underscore is a naming convention, not a security boundary.
2. Require the outcome function itself to validate a phase-specific, contract-bound authorization context—not merely that a context is an instance of a private type or carries a shared module-global object.
3. Bind development, selection, and final contexts to verified contract, database, and evaluator hashes; bind final contexts to the sealed manifest and freeze as well. Do not leave selection authorization as a no-argument convenience path.
4. Add adversarial tests that attempt direct phase-context construction and direct outcome calls with empty blocks. Empty blocks prove authorization behavior without calculating research outcomes.
5. Independently rerun both the CLI integrity path and a direct-module adversarial probe before allowing a phase transition. A selection result may remain research evidence while final access stays HOLD pending authorization repair.

## Verification Checklist

- [ ] New tests were written first and each was observed failing for the intended missing behavior.
- [ ] Legacy return fields are directly asserted unchanged.
- [ ] New cost calculation uses explicit per-side treatment and a partial-overlap turnover fixture.
- [ ] Equal-weight control uses the same eligible/liquid/censored universe and holding windows.
- [ ] Explicit research-only outcome boundary is tested.
- [ ] Focused test file and full suite passed with the required environment.
- [ ] Any external pytest basetemp was removed.
- [ ] Real evaluator was run once after tests and no unrequested report artifact was written.

## Data admission audits

When the task is an independent admission decision on a FROZEN research data
input (e.g. "Slice N admission" for a snapshot/adapter) rather than evaluator
code changes, follow `references/frozen-input-admission-audit.md`: read-only
`mode=ro&immutable=1` SQLite inspection, before/after hashes as the no-write
proof, a named-gate checklist (identity, scope, basis metadata, row integrity,
source-map completeness, backing-store reconciliation, cross-snapshot
stability), the provenance-hash-drift pitfall, and a fail-closed phase-scoped
JSON receipt. Never compute outcome metrics during a data-admission slice.

## Reference

See `references/low-vol-example.md` for a concise worked example of the low-volatility evaluator change that motivated this skill, and `references/frozen-input-admission-audit.md` for the frozen-input data admission audit recipe.
