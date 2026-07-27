# Status Publication Monotonicity

Use this matrix whenever a report-only observer preserves a current status instead of overwriting it.

## Core rule

A persisted status can suppress a candidate only when it is **fully reader-valid**, nonfuture, and at least as new by evidence time. Do not compare timestamps before validating the whole artifact.

`UNAVAILABLE` often records publication trouble at write time, not newer evidence. It must not suppress a later valid `FRESH` or `STALE` candidate solely because its timestamp is later.

## Shared validation contract

Publisher-side replacement logic and the read-only consumer must agree on:

- exact key set and schema version with exact scalar type;
- literal report-only and authority-closed fields;
- nonnegative integer counters using `type(value) is int` (JSON `true` is not an integer);
- bounded reason/text fields;
- bounded total bytes;
- timezone-aware, parseable, nonfuture evidence timestamp;
- recognized state values.

Centralize constants where practical. If implementation is split, add tests proving both sides reject the same malformed cases.

## Minimum regression matrix

1. Newer valid `FRESH`/`STALE` remains retained over older valid evidence.
2. Newer `UNAVAILABLE` yields to valid recovered evidence with an older preserved evidence timestamp.
3. Newer status missing a required field yields to valid evidence.
4. Newer status with oversized text yields to valid evidence.
5. JSON booleans in integer/version fields fail closed in the reader and cannot suppress publication.
6. Status-write failure after a successful ledger append makes the observer return `UNAVAILABLE`; isolate the status writer failure so the ledger append is demonstrably still ready.
