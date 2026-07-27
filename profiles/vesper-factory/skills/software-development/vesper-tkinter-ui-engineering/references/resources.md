# Tkinter Sources and Reusable Technology

This reference supports `vesper-tkinter-ui-engineering`. Consult official sources first; use ecosystem projects for patterns or bounded components only after the skill's technology gate.

## Official sources — implementation authority

### Python `tkinter`

- URL: <https://docs.python.org/3/library/tkinter.html>
- Role: standard Python interface to Tcl/Tk; architecture, event loop, threading model, options, geometry, bindings, images, widget classes, and window manager.
- Vesper rules derived from it:
  - Tk refreshes and handles input through its event loop.
  - Keep event callbacks short.
  - Use geometry managers rather than fixed coordinate placement for application layout.
  - Run `python -m tkinter` as a live installation/version probe.

### Python `tkinter.ttk`

- URL: <https://docs.python.org/3/library/tkinter.ttk.html>
- Role: themed widgets, widget state, style, `Treeview`, `Notebook`, `PanedWindow`, and themed controls.
- Vesper use:
  - Prefer `ttk.Treeview` for large row collections.
  - Prefer `ttk.PanedWindow` for an operator-resizable true split.
  - Prefer `ttk.Notebook` only when tabs are the selected navigation model.
  - Use classic `tk` widgets where exact Vesper dark colors or `Text` behavior matter.

### Tcl/Tk reference manual

- Index: <https://www.tcl.tk/man/tcl8.6/TkCmd/contents.htm>
- Alternate Tcl community docs: <https://www.tcl-lang.org/man/tcl8.6/TkCmd/contents.htm>
- Role: exact Tk command semantics underneath Tkinter, especially `grid`, `pack`, `bind`, `text`, `canvas`, and widget options.
- Use when Python's wrapper documentation does not answer an option or lifecycle question.

### Tk geometry and scheduling references

- Grid: <https://www.tcl-lang.org/man/tcl8.6/TkCmd/grid.htm>
- Pack: <https://www.tcl-lang.org/man/tcl8.6/TkCmd/pack.htm>
- Tcl `after`: <https://www.tcl-lang.org/man/tcl8.6/TclCmd/after.htm>
- Rule: never mix `grid` and `pack` among children of one parent. Pick the manager that fits that parent.

## High-quality learning and pattern references

### TkDocs modern tutorial

- Tutorial: <https://tkdocs.com/tutorial/index.html>
- Grid: <https://tkdocs.com/tutorial/grid.html>
- Event loop: <https://tkdocs.com/tutorial/eventloop.html>
- Styles/themes: <https://tkdocs.com/tutorial/styles.html>
- Role: modern explanations and cross-language Tk concepts.
- Useful guidance:
  - Grid fits modern aligned layouts.
  - Pack remains effective for simple one-dimensional composition.
  - Long-running work must not block Tk's event loop.
  - Complex interfaces should be decomposed into frames/classes rather than one monolithic builder.

TkDocs is educational, not a replacement for the official Python/Tcl references.

## Ecosystem decision matrix

| Project | What it provides | Good Vesper use | Avoid when |
|---|---|---|---|
| CustomTkinter | modern Tkinter-style widgets, appearance/scaling, scrollable frames, segmented controls | pattern catalog; greenfield utility app; fast high-DPI prototype | migrating VOT solely for rounded visuals; mixing two competing widget systems without benefit |
| ttkbootstrap | Bootstrap-inspired ttk themes and convenience widgets | internal tools where a coherent theme saves substantial styling code | exact VWM palette/geometry is the acceptance target |
| pygubu + pygubu-designer | XML UI definitions, visual designer, custom widgets/themes | bounded forms, settings windows, rapid layout exploration | highly dynamic card dashboards where generated XML obscures state and polling logic |
| tksheet | spreadsheet-like editable data grid | large matrix/table editing that Treeview cannot reasonably provide | ordinary status tables, cards, or read-only ranked lists |
| Matplotlib TkAgg | embedded Matplotlib figure/canvas and toolbar | analytical plots already produced with Matplotlib | tiny status trends or sparklines that a Canvas can render with less overhead |
| Pillow ImageTk | PIL images as Tk `PhotoImage`/`BitmapImage` | icons, deterministic mockups, resizing and asset processing | basic text/status UI needing no raster assets |
| sv-ttk | Sun Valley-themed ttk style | Windows-native utility windows where Vesper's custom palette is not required | VOT/VWM surfaces whose palette is already contractual |
| Tkinter Designer | Figma-derived Tkinter layout generation | disposable visual spike or asset extraction | responsive production dashboard logic, source-backed state, or maintainable hand-written architecture |

### CustomTkinter

- Documentation: <https://customtkinter.tomschimansky.com/documentation/>
- Project: <https://github.com/TomSchimansky/CustomTkinter>
- Documentation covers windows, widgets, customization, and scaling.
- Default Vesper stance: borrow interaction and hierarchy patterns; do not migrate production VOT without a measured reduction in code and a visual-compatibility spike.

### ttkbootstrap

- Documentation: <https://ttkbootstrap.readthedocs.io/en/latest/>
- Project: <https://github.com/israel-dryer/ttkbootstrap>
- Provides themed ttk widgets and additional convenience components.
- Test exact state maps, dark colors, Windows rendering, and packaging before adoption.

### pygubu and pygubu-designer

- Project: <https://github.com/alejandroautalan/pygubu>
- Designer: <https://github.com/alejandroautalan/pygubu-designer>
- Provides XML-defined interfaces plus a graphical designer and widget set.
- Useful for static forms and rapid layout variants. Keep dynamic VOT polling, signatures, source lineage, and action logic in ordinary Python even when a builder supplies the widget tree.

### tksheet

- Documentation: <https://ragardner.github.io/tksheet/DOCUMENTATION.html>
- Project: <https://github.com/ragardner/tksheet>
- Provides a spreadsheet/data-grid widget with editing, selections, validation, filtering, and CSV-oriented examples.
- Introduce only when Vesper truly needs spreadsheet semantics. `Treeview` remains simpler for read-only operational rows.

### Matplotlib embedded in Tk

- Official example: <https://matplotlib.org/stable/gallery/user_interfaces/embedding_in_tk_sgskip.html>
- Uses `FigureCanvasTkAgg` and optional `NavigationToolbar2Tk`.
- Separate chart refresh cadence from Tk's fast UI callbacks. Reuse figure/artist objects; do not create a new figure on each poll.

### Pillow ImageTk

- Documentation: <https://pillow.readthedocs.io/en/stable/reference/ImageTk.html>
- `ImageTk` creates and modifies Tk-compatible image objects from PIL images.
- Retain a Python reference to every image used by a widget; otherwise Tk may display a blank image after garbage collection.

### sv-ttk

- Project: <https://github.com/rdbende/Sun-Valley-ttk-theme>
- Applies to themed `ttk` widgets; regular `tk` widgets do not inherit full theming.
- Treat it as a utility-app option, not a VOT default.

### Tkinter Designer

- Project: <https://github.com/ParthJadhav/Tkinter-Designer>
- Generates Tkinter UI from Figma designs.
- Use only for spikes after checking current maintenance, generated-code quality, scaling, licensing, and responsive behavior. Never merge generated output without simplifying it and reconnecting authoritative data sources.

## Minimalist inspiration sources

Use these to study hierarchy and component behavior, not to copy visual fashion:

1. Official ttk widget set — platform-native states and restrained controls.
2. TkDocs complex-interface organization — frame composition and geometry discipline.
3. CustomTkinter documentation — appearance mode, scaling, segmented controls, scrollable-frame patterns.
4. ttkbootstrap gallery — theme and semantic-state ideas.
5. pygubu designer — quick spatial experiments before hand-authoring the accepted layout.
6. Existing VWM/VOT screenshots and source — Vesper's actual visual contract outranks generic galleries.

A useful inspiration pass answers:

- Which operator question becomes faster to answer?
- Which existing panel can be removed?
- Which component is reusable without hiding truth or lifecycle logic?
- Does the idea survive minimum width and maximum text scale?

If it only makes the UI look newer, reject it.

## Dependency adoption worksheet

Record this before adding a package:

```text
Capability gap:
Current stdlib approach and cost:
Candidate project + URL:
License verified on:
Latest release/activity checked on:
Windows/Tk version tested:
Prototype path:
Startup and memory result:
Resize/text-scale result:
Packaging result:
Code deleted vs code added:
Decision: ADOPT / REJECT / REVISIT
```

Do not trust stars, screenshots, or a successful `pip install` as engineering evidence.

## Prebuilt-component spike checklist

- [ ] Built outside production modules.
- [ ] Uses Vesper palette and fonts.
- [ ] Contains long, missing, error, and high-row-count states.
- [ ] Works at minimum/default/wide geometry.
- [ ] Works at maximum text scale.
- [ ] Does not block the Tk event loop.
- [ ] Does not rebuild unbounded widget trees per refresh.
- [ ] Package license and maintenance are verified from current sources.
- [ ] Windows source launch and packaged/shortcut launch both work when applicable.
- [ ] Adoption removes more complexity than it introduces.

## Source priority

When sources disagree:

1. Current Python `tkinter`/`ttk` documentation.
2. Tcl/Tk reference manual for underlying command semantics.
3. Current package documentation/source for a third-party component.
4. TkDocs for explanation and patterns.
5. Blog posts, videos, galleries, and generated examples only as inspiration.

Record the documentation URL and access date in any consequential dependency decision.
