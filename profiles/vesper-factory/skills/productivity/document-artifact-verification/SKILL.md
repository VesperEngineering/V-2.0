---
name: document-artifact-verification
description: Verify and publish generated document artifacts (especially Markdown-to-PDF) with source-of-truth, content, reproducibility, and distribution parity checks.
version: 1.0.0
---

# Document Artifact Verification

## Use when

Use this skill when asked whether a generated PDF/document is current, when regenerating a release-ready document artifact, or when copying a governed document to a distribution location.

This is not simple file-existence checking. “Up to date” means the source, the rendered artifact, the implementation/operational facts it describes, and any distributed copy agree.

## Invariants

1. The editable source is authoritative; rendered PDFs are exports.
2. A committed artifact is not proof of currentness after later source or implementation changes.
3. A matching file name or modification date is not proof of byte identity.
4. Extracted text and page count prove parseability, not factual accuracy; compare factual claims to the live source of truth first.
5. Do not claim a copied Downloads/release artifact exists or matches until its exact hash has been measured.

## Governed Markdown and Roadmap Artifacts

For Markdown architecture roadmaps, operating-model documents, or other source documents distributed outside the repository:

1. Treat the repository Markdown as the authoritative editable source; a Desktop/Downloads copy is a distribution artifact, not a second source of truth.
2. Fact-check time-sensitive claims against live scheduler state, receipts, manifests, and runtime artifacts before writing. Distinguish a real execution proof from a canonical tracked producer.
3. If the user means “the whole workflow,” do a completeness pass before rendering. Include the control plane, human authority, workforce/roles, task state machine, code-delivery lifecycle, research lifecycle, paper/evidence lifecycle, approvals, schedules, watchdogs, recovery, operator playbook, current state, and open decisions. A topology diagram or two-system map alone is not a whole workflow.
4. If labels such as V2/V3 are not formal release versions, say so explicitly and define the operational meaning of each label.
5. Include one clear first implementation slice, acceptance chain, non-goals, and preserved authority boundaries. Avoid documenting an aspirational autonomous architecture without a path from the current evidence.
6. For visual document work, render a page preview before running the final suite. Prefer a browser print engine (Chromium/Playwright) with selectable text and inline SVG over a basic PDF library when typography or diagrams matter. Keep one major diagram per page, avoid fixed-position footers that can overlay body text, and inspect the cover, every diagram class, a dense content page, and the final page.
7. When copying the document to a requested local surface, compare exact SHA-256 hashes and report byte identity. Leave unrelated dirty repository files untouched.
8. If the repository governs documentation changes, stage and commit the authoritative source, maintained renderer, focused tests, and generated repository artifact only; do not bundle downloaded copies, local data, credentials, or unrelated artifacts.

### Renderer setup and reproducibility

If the project has no dependency manifest, make the renderer’s missing-dependency error self-describing rather than inventing a new project-wide requirements convention. For Chromium rendering, the one-time setup is:

```text
<project-venv>/Scripts/python.exe -m pip install playwright
<project-venv>/Scripts/python.exe -m playwright install chromium
```

Record the exact regeneration command in the authoritative source or renderer help. The renderer should accept explicit source/output paths so an isolated temporary-root run can prove reproducibility.

For the concrete Vesper Markdown-roadmap renderer, visual preview, PyMuPDF, hash-parity, and Desktop-distribution recipe, see `references/vesper-roadmap-pdf-recipe.md`. For complete governed-repository workflow diagrams delivered as standalone Desktop HTML, see `references/governed-repository-workflow-map.md`.

## Workflow

1. **Identify authority and scope.**
   - Read repository governance instructions before changing tracked artifacts.
   - Locate the editable source, renderer, repository artifact, and each requested distribution copy.
   - Inspect repository status and the last documentation commit. Separate unrelated dirty files from the intended documentation slice.

2. **Fact-check the source before rendering.**
   - Enumerate time-sensitive claims: schedules, job counts, worktree counts, release status, feature state, safety gates, and paths.
   - Compare them to live configuration, code anchors, and operational state—not prior assistant summaries.
   - Resolve internal contradictions too (for example, a “pending” table row versus a later “done” section).
   - Update the authoritative source first. Keep ongoing evidence accrual or human decisions distinct from completed implementation work.

3. **Render deterministically and preview visually.**
   - Use the repository’s renderer and pinned/project interpreter where available.
   - Render to the repository artifact, then copy that exact output to the requested distribution location.
   - Do not hand-edit a PDF after rendering.
   - For creative/visual PDF work, do not run tests or linters before the user has approved the visual direction unless you are at the commit gate. Preview first, then validate after sign-off.
   - Use screenshot/raster inspection as a layout check only; retain PDF text/vector parsing as the artifact check.

4. **Run focused and isolated verification.**
   - Run the focused renderer test and compile check first.
   - If the environment’s verification marker explicitly asks for `pytest`, invoke the repository’s actual pytest executable (for example, `.venv/Scripts/pytest.exe tests/test_renderer.py -q`) rather than relying only on a wrapper or an older suite result.
   - Create a temporary script with an OS-safe temporary path and a `hermes-verify-` prefix.
   - Copy the source and renderer into a temporary root; execute the renderer there so verification does not depend on the already-generated governed artifact.
   - Assert: renderer exit success, output begins with `%PDF-`, a real PDF parser opens it, page count is positive, normalized extracted text contains chosen current-operation tokens, and expected vector/diagram content is present when diagrams are a requirement.
   - Compare SHA-256 of the repository artifact and every distributed copy. Require byte identity when the distribution is supposed to be an exact copy.
   - Delete the temporary script/root and report this as **ad-hoc verification**, not suite green.
   - For a large full suite on Windows, use a tracked background process and wait/poll to completion rather than allowing a foreground wrapper timeout to erase buffered pytest output.

5. **Commit deliberately.**
   - Stage only the authoritative source and generated artifact; do not commit downloaded copies, local data, credentials, or unrelated workspace residue.
   - Generated PDFs can make whitespace-oriented text hooks noisy; run text checks on the source and verify the PDF through parser/hash checks instead.
   - Commit/push only after the verification above passes. Report the exact commit and artifact hash.

## Reporting format

Give a direct yes/no answer first. Then state:

- authoritative source and repository artifact paths,
- substantive corrections made, if any,
- PDF parse/page/token result,
- distribution-copy hash equivalence,
- whether verification was ad-hoc or a canonical suite,
- commit/push result when applicable.

Avoid saying “fully verified” merely because the renderer printed success or a test suite unrelated to the renderer passed.

## Pitfalls

- Shell pipelines may mask the renderer/test exit code; inspect the real process result or run the final verification without a pipe.
- PDF text extraction can insert line breaks within sentences; normalize whitespace before token checks.
- Do not run generic whitespace validation against a binary PDF; it can report meaningless diagnostics from the PDF stream.
- Do not encode transient source values such as a particular job count or artifact hash into this skill. Verify them afresh each release.

See `references/three-way-document-check.md` for a concise evidence matrix.
