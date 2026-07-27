# Vesper Markdown Roadmap PDF Recipe

Use this recipe for a governed Markdown architecture/roadmap document that needs a readable PDF on a local operator surface.

## Canonical pattern

1. Keep the Markdown source authoritative in `D:/vesper/docs/`.
2. Do not reuse a specialized renderer for a different document family. Create a dedicated renderer with explicit `--source` and `--output` arguments.
3. Use the project interpreter and Playwright/Chromium so text remains selectable and tables/code blocks render predictably.
4. Keep the renderer deterministic: a small print CSS theme, a cover, page breaks at major sections, and no hand-edited PDF.
5. Put the exact regeneration command in the Markdown source or renderer help.
6. Render the canonical repo PDF first, then copy that exact file to Desktop/Downloads as distribution.

## Verification recipe

```text
D:/vesper/.venv/Scripts/python.exe -m py_compile scripts/render_<document>_pdf.py tests/test_render_<document>_pdf.py
D:/vesper/.venv/Scripts/python.exe -m pytest tests/test_render_<document>_pdf.py -q
D:/vesper/.venv/Scripts/python.exe scripts/render_<document>_pdf.py --source <source.md> --output <repo.pdf>
copy <repo.pdf> <Desktop.pdf>
```

Then use PyMuPDF (`fitz`) to assert:

- the file starts with `%PDF-`;
- the parser opens it;
- page count is positive;
- extracted text contains current-operation tokens and the regeneration command;
- repo and distribution copies have identical SHA-256 hashes.

Make a visual preview/contact sheet of the cover, a dense table/content page, a roadmap/diagram page, and the final page. Inspect for clipping, overlap, blank pages, and source-anchor visibility. Visual inspection supplements parser/hash checks; it does not replace them.

## Repository hygiene

Stage only the authoritative Markdown, dedicated renderer, focused renderer test, and canonical repo PDF. Do not stage the Desktop copy, preview images, credentials, generated test residue, or unrelated dirty worktree files. Commit/push the curated slice when repository governance requires it.

## Vesper-specific example

- Source: `docs/VESPER_V2_TO_V3_AUTONOMY_ROADMAP.md`
- Renderer: `scripts/render_v2_to_v3_roadmap_pdf.py`
- Repo artifact: `docs/VESPER_V2_TO_V3_AUTONOMY_ROADMAP.pdf`
- Desktop artifact: `C:/Users/bgonn/Desktop/VESPER_V2_TO_V3_AUTONOMY_ROADMAP.pdf`
- Proof: PyMuPDF parse/text checks, 14-page result, visual final-page check, and identical SHA-256 hashes.
