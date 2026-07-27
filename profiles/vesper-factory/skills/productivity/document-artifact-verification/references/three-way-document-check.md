# Three-way document-currentness check

Use this matrix before answering “is the PDF current?”

| Layer | Evidence | Pass condition |
|---|---|---|
| Operational facts | Live configuration, code anchors, and repository state | Every mutable claim in the editable source matches observed state; contradictions are corrected. |
| Source → rendered artifact | Isolated renderer run in a temporary root; PDF parser and normalized-text token checks | Renderer succeeds; output has `%PDF-`; parser opens it; page count is positive; selected current claims appear. |
| Repository artifact → distribution copy | SHA-256 of both files | Exact same digest when the copy is intended to be identical. |

## Minimal temporary-verifier design

1. Allocate a temp script and temp root using the platform's safe temporary-file APIs; name the script `hermes-verify-*`.
2. Copy only the editable source and renderer to the root.
3. Run with the project interpreter from the temp root.
4. Parse the temporary output using `pypdf` or PyMuPDF.
5. Normalize whitespace in extracted text before phrase/token assertions.
6. Hash the governed artifact and every released/distributed copy.
7. Delete temporary files even after a failed check; report the failure rather than inferring success from an older artifact.

## Whole-workflow completeness checklist

When the user asks for the entire agentic workflow rather than an architecture slice, require all of these source sections before calling the PDF complete:

- authority hierarchy and approval surfaces;
- workforce roles, specialist ownership, review separation, and skill/authority distinction;
- durable task/work-packet state machine;
- implementation and code-delivery lifecycle;
- research direction, queue/lease, experiment, artifact, candidate, and downstream review path;
- data/factor/paper-evidence lifecycle, including weekly tuning and monthly review;
- operator surfaces, ledger parity, cron estate, receipts, watchdogs, alerting, and recovery;
- current implementation map, remaining evidence accrual, open human decisions, and final invariant.

A two-system topology diagram plus a cron table is an overview, not a whole-workflow document.

## Visual PDF quality check

For a diagram-heavy PDF, inspect rendered page images before the final test/commit gate:

1. Cover: title and scope are explicit.
2. Every diagram class: labels/arrows are readable at normal zoom; no clipping.
3. Dense content page: tables and body copy are not blurry or overlaid.
4. Final page: no orphan metadata, fixed-footer overlap, or blank artifact page.

Prefer one major diagram per page. Inline SVG rendered through Chromium keeps diagram text/vector edges sharp; fixed-position HTML footers are a known source of page-content overlap.

## Evidence wording

- Say **“ad-hoc verification passed”** for this temporary probe.
- Say **“canonical suite passed”** only when the project owns a documented test command that exercises this behavior.
- If a copy was not found or hashes differ, answer “No” regardless of whether the repository PDF itself parses.

