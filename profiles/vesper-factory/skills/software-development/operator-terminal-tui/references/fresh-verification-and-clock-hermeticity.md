# Fresh verification and hermetic clock gates

Use this when a complete suite passes but the same safety tests fail in a fresh focused process.

## Verdict rule

A full-suite pass is not release evidence if an independently launched focused safety slice fails. Treat the focused failure as evidence of test-order dependence, leaked process state, or an incompletely injected boundary—not as noise.

## Verification sequence

1. Run the changed focused slice in a fresh process with cache disabled and a unique `--basetemp`.
2. Run the complete suite.
3. Rerun the focused slice in another fresh process.
4. Require all three to pass from a clean committed candidate.

This catches suites that borrow module globals, environment variables, caches, monkeypatches, or unstaged implementations from earlier tests.

## Canonical-clock pattern

- Inject one aware `now`/clock at the production admission boundary and thread it through calendar, market-session, receipt-date, and provider-timestamp checks.
- Do not patch only the caller module's imported `datetime` when a calendar/session service reads its own clock.
- Avoid a mix of injected time and direct `datetime.now()` calls in one decision path.
- Use timezone-aware fixtures and convert semantically at the boundary under test.

## Negative-test authority

A fail-closed result is not enough. A negative test must also assert:

- the exact intended failure reason or gate;
- zero downstream broker/provider/mutation calls;
- no durable state transition beyond the expected blocked receipt.

Otherwise an earlier unrelated gate can make the test green while the target defect remains reachable.

## Diagnosis checklist

- Compare environment variables and module globals between full and focused runs.
- Look for module-level cached aliases captured before monkeypatching.
- Identify every independent clock owner.
- Check autouse fixtures for wrong-module patch targets.
- Run the single failing test and its whole file both alone and after likely contaminating files.
- Repair the production injection boundary or fixture; never weaken the expected reason merely to accept an earlier block.
