# Cross-Surface Command Deck Redesign

Use this reference when a Prompt Toolkit operator terminal must inherit an accepted native monitor's visual system without weakening the terminal's evidence, governance, or responsive contracts.

## Boundary first

Prefer this architecture when it already exists:

```text
immutable snapshot → pure renderer → controller / overlays → Prompt Toolkit app
```

A first visual pass should stay in the pure renderer and style table. Do not touch telemetry loaders, provider services, approval logic, broker/scheduler gates, or controller mutation paths unless a failing renderer test proves an authoritative field is missing.

Before editing, confirm the relevant renderer/controller/launcher paths are clean or isolate them in a named worktree. A dirty canonical repo is not a reason to race unrelated owners.

## Structural palette versus semantic palette

Translate the accepted native visual system by role:

| Structural role | Color |
|---|---:|
| black | `#090a0a` |
| near | `#0d0f10` |
| charcoal | `#141718` |
| panel | `#191c1d` |
| raised | `#202426` |
| line | `#303536` |
| strong line | `#454a4b` |
| muted | `#858988` |
| soft | `#b9b8b2` |
| warm white | `#eeeae1` |
| white | `#f7f3ea` |
| rail/accent | `#ff7819` |

Keep semantic colors separate: green/pass, red/blocked or failed, amber/stale or waiting, blue/running, purple/delegated. Orange is a structural rail/accent unless the product contract explicitly assigns it a state meaning.

Every state keeps a text/symbol label; color is never the only carrier.

## Redesign means information architecture

Do not call a palette swap or different column weights a redesign. A Command Deck should visibly implement this scan order:

```text
status band
    ↓
primary blocker ───────── workforce rail
    ↓                         ↓
evidence spine             Kanban
    ↓                         ↓
account / data / authority next safe
    ↓                         ↓
provider / receipts        recent activity
    ↓
issues / approvals
```

Use one dominant operations canvas and one dedicated workforce rail. Move verbose system/provider prose behind existing overlays while keeping compact capacity, freshness, source scope, and authority visible by default.

## Protected truths

Before changing the default frame, list and test the truths that must survive:

- environment/posture (`LOCAL / GOVERNED`, paper/live, market/session);
- authority state and independently closed execution gates;
- observed timestamp and snapshot freshness;
- first incomplete gate with state, detail, freshness, source path, and next safe action;
- ordered evidence-chain state;
- provider provenance: OpenAI workspace/session, OpenRouter account/key/credits, local receipts;
- worker phase, blocker reason, Kanban vocabulary, next-safe fields, and bounded activity;
- embedded Issues/Approvals are selection queues, not mutation surfaces;
- exact-scope review remains separate from execution authority;
- hidden reasoning, credentials, prompts, and unfiltered tool output remain excluded.

Preserve exact IDs and paths in overlays or detail views; default cards may use bounded human labels.

## Target geometry and responsive levels

For the current VOT desktop contract, validate the real launcher at `2500×1015 px` and approximately `312×63` cells. Also probe `180×50`, `140×40`, `120×35`, and `90×25`.

Give zoom levels semantic roles rather than only more rows:

- **Focused:** status, blocker, evidence, next safe, workforce/Kanban.
- **Balanced:** add account/data/authority, compact provider, activity, governed queues.
- **Detail:** add system details, expanded provider/receipt/cadence rows.

At narrow widths, preserve authority, blocker, provider provenance, and footer shortcuts before optional detail.

## Renderer-first TDD

1. Write a failing region-order test at the authoritative grid.
2. Assert exact row count, maximum width, footer position, and absence of unintended ellipses.
3. Add structural style-fragment tests for brand, headings, borders, and rail token while preserving existing state/activity/worker class names.
4. Add blocker-field tests (`STATE`, `GATE`, `FRESHNESS`, `SOURCE`, `NEXT`).
5. Add evidence-spine wrapping tests.
6. Add worker continuation-alignment and Kanban-vocabulary tests.
7. Add zoom-level region-presence tests.
8. Rerun controller, hardening, provider, status, and approval suites unchanged.

Do not weaken tests because the screenshot looks cleaner. Missing/stale values remain unavailable/stale, never zero/fresh.

## Visual acceptance

A pure render probe catches geometry, not visual success. After each coherent information-architecture pass:

1. retire stale titled terminal children;
2. launch the actual Desktop shortcut and canonical interpreter;
3. verify the native HWND and pseudoconsole cell grid;
4. capture a fresh screenshot;
5. reject dead space, legacy pane-sheet hierarchy, one-cell border clipping, wrapped-row spill, or hidden governance state;
6. change one bounded information-architecture idea per pass;
7. only publish after operator acceptance, focused/full/focused verification, and an independent frozen-candidate review.

## Practical styling note

A plain-string renderer can still gain structural styles by extending its formatted-text tokenizer with stable heading/brand/rail tokens. Preserve existing `class:state-*`, `class:activity-*`, and `class:worker-*` contracts. If structural styling becomes too brittle, return structured fragments from the pure renderer rather than parsing arbitrary prose after the fact.

### Pitfall: `style_state_tokens` does not style the `▌` rail glyph

The VWM orange rail token `▌` is placed in the header text (e.g.
`▌ VESPER / OPERATOR CONTROL`), and a `brand-rail` class mapped to
`#ff7819` is added to `DASHBOARD_STYLE`. However, the live app calls
`style_state_tokens()` (or `style_dashboard_tokens()`) on the rendered
text before display. That function only applies classes for tokens in
`STATE_STYLE`, `ACTIVITY_STYLE`, and `WORKER_STYLE` — it does NOT
recognize `▌` or map it to `brand-rail`.

**Result:** the `▌` appears in the text (tests pass on text content)
but renders in the default body color, not VWM orange. The style class
exists in the dict but nothing applies it to the glyph.

**Fix options (in order of preference):**

1. Add `▌` to the `DISPLAY_PATTERN` regex and map it to `brand-rail`
   in the same lookup dict used for state/activity/worker tokens.
   This is the smallest change and keeps the existing tokenizer flow.
2. Return structured `FormattedText` fragments directly from the
   header builder, with `("class:brand-rail", "▌ ")` as an explicit
   prefix fragment before the rest of the line.
3. Use a dedicated header-rendering function that wraps the rail glyph
   in the correct class without relying on the generic tokenizer.

A test that only asserts `lines[0].startswith("▌ VESPER")` will pass
even when the glyph is unstyled. To verify the style is actually
applied, assert that the `FormattedText` fragments for line 0 contain
a fragment with `class:brand-rail` — not just that the text is present.
