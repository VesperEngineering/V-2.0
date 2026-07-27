# Authoritative Historical Exchange-Calendar Evidence

Use this playbook when a deterministic session calendar must be proven for a historical range and the exchange's live page shows only current/future years.

## Evidence standard

A defensible calendar evidence set must distinguish:

- **Authority:** the exchange, its rulebook, or the exchange owner's official press site.
- **Transport:** a live HTTPS fetch or a content archive such as Wayback.
- **Corroboration:** market-data absence, federal proclamations, third-party libraries, and news articles. These can reveal a missing date but do not establish the exchange schedule by themselves.

Never label an archive, search engine, market-data vendor, or federal calendar as the exchange authority. Record the original official URL separately from the archive URL and capture timestamp.

## Recovery procedure

1. **Freeze the supported date range.** Name the first/last supported year and whether the artifact needs full-day sessions only or early-close times as well.
2. **Capture the live rule and calendar.** Save raw bytes, SHA-256, retrieval time, URL, relevant rule amendment dates, and displayed years. Do not extrapolate historical dates from a page that only displays future years.
3. **Index archived official pages.** Query the archive CDX index for the official calendar URL across the target years. Save and hash the index response. Choose snapshots whose rendered official table explicitly covers each year; overlapping annual tables provide useful redundancy.
4. **Handle legacy dynamic pages without guessing.** If a capture has only a JavaScript shell, inspect embedded component JSON for `partialPageURL`, `ajaxUrl`, or named data endpoints and retrieve those archived payloads. If the payload still lacks the closure table, use a later official capture that displays the target year. Do not reconstruct dates from a generic holiday formula merely because the old UI is inconvenient.
5. **Recover exceptional closures separately.** Annual recurring-holiday tables often omit one-off national-day, weather, or emergency closures. Query the archive by the official press-release directory prefix, enumerate official-origin URLs, select the release by title/date, and capture its full bytes. Prefix discovery is more reliable than guessing an exact slug.
6. **Extract an exact closure map.** For each supported year, store sorted full-day closure dates. Record the source snapshots that cover that year, observance footnotes, rule changes, and exceptional-release claims. Keep early-close days in the session set unless the contract explicitly models session times.
7. **Cross-check code by exact set equality.** Generate every weekday for each year and require `weekdays - generated_sessions == evidenced_full_day_closures`. Also reject unexpected non-session input dates and wholly missing expected sessions in the observed panel span.
8. **Version on any semantic change.** A newly discovered closure changes session offsets, labels, features, datasets, and downstream manifests. Create a new calendar/evidence version and new artifact paths; do not silently overwrite a previously hashed v1 identity.
9. **Bind leaves before parents.** Hash authority captures and the calendar evidence manifest first, bind their paths/hashes into the closed protocol, then derive protocol, dataset, feature, release, staged-diff, and independent-review identities. Any edit to a leaf makes every descendant stale.

## Recommended evidence-manifest fields

- schema and calendar version;
- supported range;
- official origin allowlist;
- explicit `archival_transport_is_not_authority` flag;
- rule URL, raw SHA-256, relevant text claim, and amendment date;
- archive-index URL and SHA-256;
- per-snapshot origin URL, archive URL/timestamp, SHA-256, and covered years;
- per-exception date, official release URL, archive URL/timestamp, SHA-256, and exact closure claim;
- complete sorted `full_day_closures` map;
- generated-calendar equality result;
- explicit statement that unknown/unproven exceptional dates were not added.

## XNYS example learned from a 2014–2025 audit

- Archived official NYSE annual tables directly covered recurring closures for every year from 2014 through 2025.
- Juneteenth first appeared as a full-day NYSE closure in the 2022 table, consistent with the Rule 7.2 amendment dated September 30, 2021.
- The recurring tables did not contain the two one-off closures. Archived official ICE/NYSE releases were required for:
  - 2018-12-05 — National Day of Mourning for President George H. W. Bush;
  - 2025-01-09 — National Day of Mourning for former President Jimmy Carter.
- Exact-set testing exposed the missing 2025-01-09 closure in the in-repository calendar.
- NYSE's Saturday New Year's convention is not equivalent to blindly observing every Saturday federal holiday on Friday; preserve the published table/footnote behavior.

These dates are a dated example, not a substitute for recapturing and hashing the authority sources for a new protocol range.

## Fail-closed conditions

Remain HOLD when any supported year lacks an explicit official table/rule basis, an exceptional closure is supported only by non-exchange reporting, source bytes cannot be recovered or hashed, the evidence map differs from generated sessions, or the protocol hash was calculated before the final evidence binding.
