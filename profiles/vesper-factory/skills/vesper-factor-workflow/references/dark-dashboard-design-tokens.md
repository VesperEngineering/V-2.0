# Dark Dashboard Design System

Reusable design tokens and layout patterns for dark-themed financial/ops dashboards
in the Vesper ecosystem. Derived from the Vesper Factor Dashboard v2.0.0 reference
screenshot. Applies to both Tkinter (Python) and HTML (standalone) implementations.

## Color Tokens

| CSS Variable | Hex | Tkinter Constant | Usage |
|---|---|---|---|
| `--bg-primary` | `#0a0a0a` | `BG = "#0a0a0a"` | Page background |
| `--bg-secondary` | `#0d0d0d` | `BG2 = "#0d0d0d"` | Header, sidebar, footer |
| `--bg-card` | `#111111` | `CARD_BG = "#111111"` | Panel surfaces |
| `--bg-elevated` | `#1a1a1a` | `BTN_BG = "#1a1a1a"` | Button bg, hover state |
| `--bg-table-header` | `#0d0d0d` | `TH_BG = "#0d0d0d"` | Table `<thead>` |
| `--border-primary` | `#1f1f1f` | `BORDER = "#1f1f1f"` | Card/panel borders |
| `--border-secondary` | `#262626` | `BORDER2 = "#262626"` | Hover borders |
| `--border-badge` | `#333333` | `BADGE_BORDER = "#333333"` | Badge borders |
| `--text-primary` | `#ffffff` | `FG = "#ffffff"` | Headings, key values |
| `--text-secondary` | `#cccccc` | `FG2 = "#cccccc"` | Table body |
| `--text-tertiary` | `#a0a0a0` | `FG3 = "#a0a0a0"` | Icons, secondary |
| `--text-muted` | `#888888` | `FG_MUTED = "#888888"` | Labels, inactive |
| `--text-dim` | `#666666` | `FG_DIM = "#666666"` | Timestamps, muted |
| `--text-faint` | `#444444` | `FG_FAINT = "#444444"` | Disabled/unavailable |
| `--accent-green` | `#22c55e` | `GREEN = "#22c55e"` | RUNNING, positive, HEALTHY |
| `--accent-blue` | `#3b82f6` | `BLUE = "#3b82f6"` | Active nav, selection |
| `--accent-red` | `#ef4444` | `RED = "#ef4444"` | Negative trends, errors |
| `--accent-grey` | `#525252` | `GREY = "#525252"` | IDLE, neutral dots |

No gradients. No glassmorphism. No shadows on cards. Flat matte finish with 1px borders.

## Layout Specs

| Element | Value | Tkinter Equivalent |
|---------|-------|--------------------|
| Sidebar width | 220px | `Frame(width=220)` |
| Header height | 48px | `Frame(height=48)` |
| Footer height | 44px | `Frame(height=44)` |
| Card border-radius | 8px | N/A (Tkinter: flat) |
| Button/badge radius | 4px | N/A |
| Panel gap | 8px | `padx=4, pady=4` or grid spacing |
| Main padding | 10px 14px | `padx=14, pady=10` |
| Card padding | 12px 16px | `padx=16, pady=12` |
| Table cell padding | 3px 8px | `tree column width + padding` |
| Base spacing unit | 8px | `padx=N*8` pattern |

## Typography

| Role | Font | Weight | Size | Tkinter |
|------|------|--------|------|---------|
| Logo/brand | Inter | 700 | 14px | `("Segoe UI", 14, "bold")` |
| Section headers | Inter | 600 | 12px uppercase | `("Segoe UI", 12, "bold")` |
| Card labels | Inter | 600 | 10px uppercase | `("Segoe UI", 8)` |
| Metric values | Inter tabular-nums | 600 | 22px | `("Segoe UI", 22, "bold")` |
| Table body | Inter tabular-nums | 400 | 11px | `("Segoe UI", 10)` |
| Table headers | Inter | 600 | 10px uppercase | `("Segoe UI", 9, "bold")` |
| Timestamps | SF Mono / Consolas | 400 | 11px | `("Consolas", 10)` |
| Badges | Inter | 500 | 10-11px | `("Segoe UI", 9)` |
| Buttons | Inter | 500 | 11px | `("Segoe UI", 10)` |
| Log entries | SF Mono / Consolas | 400 | 11px | `("Consolas", 9)` |

Tkinter font rule: use TUPLES, never strings. `("Segoe UI", 10)` not `"Segoe UI 10"`.

## Layout Grid (Bento-Grid Pattern)

```
┌──────────────────────────────────────────────────┐
│ HEADER: logo + status pills + timestamp          │
├──────┬───────────────────────────────────────────┤
│SIDE  │ METRICS: 4 equal cards + 140px sparkline  │
│BAR   ├───────────────────────────────────────────┤
│220px │ MIDDLE 3-col: Leaders | Jobs | Portfolio  │
│      ├───────────────────────────────────────────┤
│      │ BOTTOM 3-col: Basket | Data | Activity    │
├──────┴───────────────────────────────────────────┤
│ FOOTER: action buttons (Refresh, Pipeline, etc.) │
└──────────────────────────────────────────────────┘
```

CSS: `grid-template-columns: 220px 1fr; grid-template-rows: 48px 1fr 44px`.
Panel rows: `grid-template-columns: 1fr 1fr 1fr; gap: 8px`.
Metrics row: `grid-template-columns: repeat(4, 1fr) 140px; gap: 8px`.

## Status Indicators

### Dots
- Green (`#22c55e`): RUNNING, HEALTHY, Connected, positive
- Grey (`#525252`): IDLE, neutral, inactive
- Size: 6px diameter, `border-radius: 50%`

### Badges/Pills
- Green badge: `bg #0f2e1f, color #22c55e` → OPEN, positive state
- Grey badge: `bg #1f1f1f, border 1px #333, color #a0a0a0` → PAPER, neutral state
- Radius: 4px, padding: 2px 8px

### Buttons
- Default: `bg #1a1a1a, border 1px #333, color #888`
- Hover: `bg #262626, border #444, color #fff`
- Radius: 4px, padding: 5px 12px

### Nav Items
- Active: `bg #1a1a1a, color #fff`, 3px blue (`#3b82f6`) left accent bar
- Inactive: transparent, `color #888`, hover to `#ccc`

## Trend Color Encoding

- Positive trend: `#22c55e` (green)
- Negative trend: `#ef4444` (red)
- Zero/flat: `#666666` (dim grey)

## Viewport Budget (1920×1080)

- Total: 1080px height
- Header: 48px
- Footer: 44px
- Available for main: 988px
- Dashboard content (this spec): ~803px
- Headroom: ~185px — fits without scrolling

## Screenshot-to-Dashboard Workflow

When building a dashboard from a reference screenshot:
1. `vision_analyze` with a forensic prompt: "Describe every pixel: colors, spacing,
   fonts, border radii, layout grid, icon style, table styling, data viz"
2. Build as standalone HTML with embedded CSS/JS and inline SVG icons
3. `browser_navigate` to verify structure
4. `browser_vision` to audit against reference — list every mismatch
5. Iteratively compact with `patch` tool until all panels fit 1080p viewport
6. Target ~800px content height for bento-grid dashboards