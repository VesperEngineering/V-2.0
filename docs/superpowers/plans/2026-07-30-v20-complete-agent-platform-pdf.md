# V20 Complete Agent Platform PDF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate and verify a five-page vector PDF that accurately diagrams the complete native V20 agent platform.

**Architecture:** A temporary ReportLab generator will draw reusable schematic primitives and five page-specific diagrams directly from the approved design. The final PDF is the only generated deliverable; temporary source and rendered PNGs remain under `tmp/pdfs/` for verification and are removed after acceptance.

**Tech Stack:** Python 3, ReportLab, pypdf, pdfplumber, Poppler (`pdftoppm` and `pdftotext`), PowerShell.

## Global Constraints

- Final output: `output/pdf/v20-complete-agent-platform.pdf`.
- Five pages: one 17 by 11 inch master poster plus four 11 by 8.5 inch landscape detail pages.
- Use only live `vesper/platform/`, `profiles/native/`, ADR-0001, ADR-0002, and focused tests as architecture evidence.
- Use vector lines, shapes, and text; no rasterized page backgrounds.
- Minimum text size: 8 points on the poster and 9 points on detail pages.
- Use ASCII hyphens only.
- Do not modify runtime source, profiles, protected data, configuration, or existing user changes.
- Do not claim a path, command, node, permission, or state transition that is absent from the live checkout.

---

### Task 1: Confirm Build Inputs and Toolchain

**Files:**
- Read: `vesper/platform/workflow.py`
- Read: `vesper/platform/cli.py`
- Read: `vesper/platform/service.py`
- Read: `vesper/platform/composition.py`
- Read: `vesper/platform/persistence.py`
- Read: `vesper/platform/evidence.py`
- Read: `vesper/platform/memory.py`
- Read: `vesper/platform/knowledge.py`
- Read: `profiles/native/*/profile.yaml`
- Read: `docs/adr/ADR-0001-native-langgraph-platform.md`
- Read: `docs/adr/ADR-0002-obsidian-langgraph-knowledge.md`

**Interfaces:**
- Consumes: approved diagram design.
- Produces: verified node, command, profile, store, and edge inventories used by the generator.

- [ ] **Step 1: Reconfirm exact runtime nodes and edges**

Run:

```powershell
rg -n "builder\.add_(node|edge|conditional_edges)" vesper/platform/workflow.py
```

Expected: seven `add_node` calls and the documented START, conditional, correction, approval, and END edges.

- [ ] **Step 2: Reconfirm CLI commands**

Run:

```powershell
rg -n '@app\.command' vesper/platform/cli.py
```

Expected: create, status, resume, receipts, evidence, approvals, active, knowledge-sync, knowledge-search, knowledge-status, approve, reject, and cancel.

- [ ] **Step 3: Reconfirm profile IDs and permissions**

Run:

```powershell
rg -n "profile_id:|sandbox:|allowed_tools:|network_allowed:|trading_allowed:" profiles/native
```

Expected: product and risk review read-only; development workspace-write; all network and trading values false.

- [ ] **Step 4: Confirm PDF dependencies and renderer**

Run:

```powershell
python -c "import reportlab, pypdf, pdfplumber; print('pdf-python-ok')"
pdftoppm -v
```

Expected: Python import succeeds and Poppler prints its version.

### Task 2: Build the Vector PDF

**Files:**
- Create temporarily: `tmp/pdfs/build_v20_complete_agent_platform.py`
- Create: `output/pdf/v20-complete-agent-platform.pdf`

**Interfaces:**
- Consumes: verified inventories from Task 1.
- Produces: `build_pdf(output_path: pathlib.Path) -> None` and the five-page PDF.

- [ ] **Step 1: Create reusable drawing primitives**

Implement these generator interfaces:

Required interface signatures:

- `draw_box(canvas, x, y, width, height, title, lines=(), kind="controller") -> None`
- `draw_arrow(canvas, x1, y1, x2, y2, label=None, dashed=False, color=None) -> None`
- `draw_store(canvas, x, y, width, height, title, lines=()) -> None`
- `draw_boundary(canvas, x, y, width, height, title, color=None) -> None`
- `draw_legend(canvas, x, y) -> None`
- `draw_header(canvas, title, subtitle, page_number, page_size) -> None`

Use Helvetica, Helvetica-Bold, orthogonal connectors, consistent margins, and the color/shape mapping from the specification.

- [ ] **Step 2: Implement page 1 master poster**

Implement `draw_master_poster(canvas) -> None`.

Draw Operator/CLI, Controller, LangGraph Runtime, Specialists/Services, and Persistence/Knowledge as five ownership layers. Include the primary request-to-acceptance path, protected external boundaries, and page 2-5 cross-references.

- [ ] **Step 3: Implement page 2 runtime lifecycle**

Implement `draw_runtime_lifecycle(canvas) -> None`.

Draw all seven exact node IDs, integrity and authority failure exits, validation and Risk Review correction loops, shared three-attempt limit, human interrupt, cancellation, rejection, operator intervention, and acceptance.

- [ ] **Step 4: Implement page 3 specialist boundaries**

Implement `draw_specialists_and_execution(canvas) -> None`.

Draw the three native profiles, typed inputs/outputs, permissions, receipts, Docker Codex and OpenCode routes, worktree/sandbox boundaries, protected paths, cancellation, cleanup, and rollback ownership.

- [ ] **Step 5: Implement page 4 persistence and knowledge**

Implement `draw_persistence_and_knowledge(canvas) -> None`.

Draw checkpoints, LangGraph Store, receipt memory, immutable evidence, canonical Markdown, derived FTS5, immutable per-run snapshots, and controller control records as separate authority domains with directional data flow.

- [ ] **Step 6: Implement page 5 operator authority**

Implement `draw_operator_surface(canvas) -> None`.

Draw command families, lifecycle transitions, permitted local actions, approval-required actions, recovery paths, final acceptance predicate, and source legend.

- [ ] **Step 7: Generate the PDF**

Run:

```powershell
python tmp/pdfs/build_v20_complete_agent_platform.py
```

Expected: exit 0 and `output/pdf/v20-complete-agent-platform.pdf` exists with nonzero size.

### Task 3: Structural and Text Verification

**Files:**
- Verify: `output/pdf/v20-complete-agent-platform.pdf`
- Create temporarily: `tmp/pdfs/v20-complete-agent-platform.txt`

**Interfaces:**
- Consumes: generated PDF.
- Produces: page-count, metadata, parseability, and required-label evidence.

- [ ] **Step 1: Verify PDF structure**

Run:

```powershell
python -c "from pypdf import PdfReader; p='output/pdf/v20-complete-agent-platform.pdf'; r=PdfReader(p); assert len(r.pages)==5, len(r.pages); assert r.metadata.title=='V20 Complete Agent Platform'; print('pages=5 metadata=ok')"
```

Expected: `pages=5 metadata=ok`.

- [ ] **Step 2: Extract and check required labels**

Run `pdftotext` and verify page titles, seven runtime node IDs, three profile IDs, persistence domains, CLI commands, and acceptance terms are present.

```powershell
pdftotext -layout output/pdf/v20-complete-agent-platform.pdf tmp/pdfs/v20-complete-agent-platform.txt
rg -n "Master Architecture|Runtime Lifecycle|data_research|model_evaluation|human_approval|v20-product|v20-development|v20-risk-review|LangGraph Store|KnowledgeContext|knowledge-sync|ACCEPTED" tmp/pdfs/v20-complete-agent-platform.txt
```

Expected: every required expression matches.

- [ ] **Step 3: Scan for prohibited placeholders and non-ASCII dashes**

Run:

```powershell
python -c "from pathlib import Path; t=Path('tmp/pdfs/v20-complete-agent-platform.txt').read_text(); markers=['T'+'ODO','T'+'BD','PLACE'+'HOLDER','FIX'+'ME']; assert not any(m in t for m in markers); print('marker-scan=ok')"
```

Expected: no matches. Inspect extracted text for non-ASCII dash characters with a short Python assertion.

### Task 4: Render and Visually Inspect Every Page

**Files:**
- Create temporarily: `tmp/pdfs/rendered/v20-page-1.png` through `v20-page-5.png`
- Verify: `output/pdf/v20-complete-agent-platform.pdf`

**Interfaces:**
- Consumes: structurally valid PDF.
- Produces: rendered page evidence and any repaired PDF revision.

- [ ] **Step 1: Render all pages**

Run:

```powershell
pdftoppm -png -r 144 output/pdf/v20-complete-agent-platform.pdf tmp/pdfs/rendered/v20-page
```

Expected: five PNG files.

- [ ] **Step 2: Inspect all five PNGs**

Use the local image viewer on every page. Check margins, labels, connector directions, legends, page numbers, colors, minimum text size, and absence of clipping or overlap.

- [ ] **Step 3: Repair and re-render if needed**

For every defect, patch only the temporary generator, regenerate the PDF, rerun Task 3, render all five pages again, and reinspect every changed page. Repeat until the latest inspection has zero visual defects.

### Task 5: Final Reconciliation and Delivery

**Files:**
- Keep: `output/pdf/v20-complete-agent-platform.pdf`
- Remove: temporary files under `tmp/pdfs/`

**Interfaces:**
- Consumes: verified PDF and approved specification.
- Produces: final user-facing PDF with fresh verification receipt.

- [ ] **Step 1: Reconcile specification coverage**

Check every page requirement and acceptance criterion in `docs/superpowers/specs/2026-07-29-v20-complete-agent-platform-diagram-design.md` against the latest rendered PDF.

- [ ] **Step 2: Remove temporary generator and renders**

Resolve `tmp/pdfs/`, confirm it is inside the repository, assign that resolved value to `$pdfTempPath`, then remove it with `Remove-Item -LiteralPath $pdfTempPath -Recurse -Force`.

- [ ] **Step 3: Run final verification**

Re-run the five-page pypdf assertion, required-label extraction, `git diff --check`, and `git status --short`. Confirm no existing user change was altered.

- [ ] **Step 4: Deliver**

Provide a clickable link to the final PDF, summarize the five pages, state the fresh page/text/render checks, and identify any residual scope limitation.
