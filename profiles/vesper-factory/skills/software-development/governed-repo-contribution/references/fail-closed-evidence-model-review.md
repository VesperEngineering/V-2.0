# Adversarial review of fail-closed evidence models

Use this profile when code converts untrusted operational evidence into operator-visible state, completion, approvals, objectives, or action receipts.

## Frozen-candidate sequence

1. Record the base SHA, candidate SHA, clean worktree state, and exact `base..candidate` range.
2. Run focused tests and adversarial probes against that frozen candidate.
3. Treat malformed or missing reviewer output as no-verdict; treat explicit blocking findings as FAIL.
4. Preserve failed candidate SHAs. Repair with a successor commit and review the new full range.
5. Never integrate until an independent reviewer explicitly passes the exact frozen candidate.
6. After two failed review/fix cycles, stop autonomous churn and present the cumulative rejection history plus one recommendation before continuing.

## Boundary probe matrix

- **Exact booleans:** reject `0`, `1`, `None`, strings, containers, and arbitrary objects where exact `True`/`False` carries completion or authority meaning.
- **IDs/text:** reject empty, padded, repeated-whitespace, tab/newline, NUL/DEL, control characters, malformed types, subclasses, and unhashable objects. Type-check before equality so hostile `__eq__` cannot escape.
- **Timestamps:** reject non-finite/overflow values, hostile numeric subclasses, and malformed or hostile `tzinfo`; return fail-closed state rather than raising.
- **Hashability:** hash the complete immutable model, not only a nested signature. Probe hostile scalar subclasses and malformed source fields.
- **Duplicate identities:** contradictory duplicates stay visible and unselected; never rely on last-write-wins for safety state.
- **Source posture:** validate completeness by state. `FRESH` requires nonempty parseable observation evidence and nonempty provenance; the enum value alone is not freshness proof.
- **Exception totality:** public state, receipt, and objective resolvers must return a fail-closed result for malformed runtime values, including hostile `__eq__`, `__hash__`, conversion, and timezone behavior.
- **Documentation truth:** distinguish deployed current behavior from target contracts. Do not claim a defect is closed before the frozen candidate passes adversarial review.

## Full-suite interpretation

Compare base and candidate under equivalent environment and fixtures. Classify failures as candidate regression, pre-existing baseline failure, environment/fixture dependency, or no-verdict. Focused green tests plus unexplained full-suite failures are not an integration PASS.

## Review artifact UX

Persist the complete reviewer output as a file. If the user asks to **open**, **pull up**, or **show the review document**, launch that exact report artifact in the desktop application. Do not substitute an engineering plan, master architecture document, prose summary, or approval menu. After opening, report only the exact path and verdict.
