# Tkinter node-and-connector progress visualization

Use a `tk.Canvas` to render a multi-stage pipeline as connected rounded-rectangle nodes. This is clearer than ASCII arrows or stacked circles for research-console training progression.

## When to use

- A compact dashboard needs to show stages: Data → Train → Eval → Report.
- Stages have distinct states: `pending`, `active`, `complete`.
- The visualization must resize with the window and remain legible at small widths.

## State contract

Expose one function that returns a stable `(title, detail, stages)` tuple:

```python
def training_stage_state(current: dict[str, Any] | None) -> tuple[str, str, list[dict[str, str]]]:
    status = current.get("status") if current is not None else None
    phase = current.get("phase", "").lower() if current is not None else ""

    if status == "RUNNING":
        return "Training in progress", "Live run; weights are updating.", [
            {"label": "Data", "status": "complete"},
            {"label": "Train", "status": "active"},
            {"label": "Eval", "status": "pending"},
            {"label": "Report", "status": "pending"},
        ]
    if status == "EVALUATING":
        return "Evaluating adapter", "Frozen comparison running.", [
            {"label": "Data", "status": "complete"},
            {"label": "Train", "status": "complete"},
            {"label": "Eval", "status": "active"},
            {"label": "Report", "status": "pending"},
        ]
    if status == "COMPLETE" or "completed" in phase:
        return "Run completed", "Receipt saved; review before promotion.", [
            {"label": "Data", "status": "complete"},
            {"label": "Train", "status": "complete"},
            {"label": "Eval", "status": "complete"},
            {"label": "Report", "status": "complete"},
        ]
    return "Awaiting dataset admission", "No model weights trained.", [
        {"label": "Data", "status": "pending"},
        {"label": "Train", "status": "pending"},
        {"label": "Eval", "status": "pending"},
        {"label": "Report", "status": "pending"},
    ]
```

Test the function independently of Tk.

## Canvas draw routine

```python
def _draw_training(self) -> None:
    canvas = self.training_canvas
    canvas.delete("all")
    width = max(canvas.winfo_width(), 320)
    title, detail, stages = training_stage_state(self._current)

    colors = {
        "complete": {"fill": "#4ec9b0", "text": "#1e1e1e"},
        "active":   {"fill": "#007acc", "text": "#ffffff"},
        "pending":  {"fill": "#3c3c3c", "text": "#808080"},
    }

    node_width = min(88, max(56, (width - 80) // len(stages)))
    gap = max(16, (width - len(stages) * node_width) // (len(stages) + 1))
    y, height, radius = 60, 34, 8

    for index, stage in enumerate(stages):
        x0 = gap + index * (node_width + gap)
        x1 = x0 + node_width
        style = colors[stage["status"]]

        # connector from previous node
        if index > 0:
            prev_x1 = gap + (index - 1) * (node_width + gap) + node_width
            line_color = "#4ec9b0" if stage["status"] == "complete" else "#3c3c3c"
            canvas.create_line(prev_x1 + 2, y + height // 2, x0 - 2, y + height // 2,
                               fill=line_color, width=3)

        # rounded rectangle via smooth polygon
        def _rounded(x0, y0, x1, y1, r, **kw):
            return canvas.create_polygon(
                x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
                x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
                x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
                smooth=True, **kw,
            )

        _rounded(x0, y, x1, y + height, radius, fill=style["fill"], outline="")
        canvas.create_text((x0 + x1) // 2, y + height // 2, text=stage["label"],
                           fill=style["text"], font=("Segoe UI", 9, "bold"))

        caption_color = {"complete": "#4ec9b0", "active": "#9cdcfe", "pending": "#808080"}[stage["status"]]
        canvas.create_text((x0 + x1) // 2, y + height + 14, text=stage["status"].upper(),
                           fill=caption_color, font=("Segoe UI", 7))

    canvas.create_text(8, 8, anchor="nw", text=title, fill="#9cdcfe", font=("Segoe UI", 9, "bold"))
    canvas.create_text(8, 146, anchor="sw", text=detail, fill="#a0a0a0", font=("Segoe UI", 8))
```

Bind `<Configure>` so the diagram redraws on resize:

```python
self.training_canvas.bind("<Configure>", lambda _event: self._draw_training())
```

## Key design points

- Derive `node_width` and `gap` from the actual canvas width; cap minimums so labels do not clip.
- Use `winfo_width()` with a fallback (`max(..., 320)`) because an unmapped canvas returns `1`.
- Color-code by semantic state, not by stage index.
- Show status captions (`PENDING` / `ACTIVE` / `COMPLETE`) below each node so the diagram is self-explanatory.
- Keep the title and detail as plain text inside the same canvas; this avoids extra widget layout complexity.

## Verification

- Unit-test `training_stage_state` for every status/phase combination.
- Compile the console module with `py_compile`.
- Run `--smoke-test` to exercise state loading and drawing without opening a persistent window.
- Launch the real Desktop shortcut and assert a titled window appears and responds.

## Inference-path companion

For a research-only inference flow, draw a second Canvas with boxes and arrows:

```python
def _draw_inference(self) -> None:
    canvas = self.inference_canvas
    canvas.delete("all")
    width = max(canvas.winfo_width(), 320)
    boxes = ("Thesis", "Specialist\nmodel", "Schemas +\ntools", "Research\npackage")
    box_width = max((width - 44) // len(boxes) - 8, 54)
    y0, y1 = 42, 95
    for index, label in enumerate(boxes):
        x0 = 8 + index * (box_width + 11)
        x1 = x0 + box_width
        fill = "#264f78" if index == 1 else "#252526"
        canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline="#569cd6")
        canvas.create_text((x0 + x1) // 2, (y0 + y1) // 2, text=label,
                           fill="#d4d4d4", font=("Segoe UI", 8, "bold"))
        if index < len(boxes) - 1:
            canvas.create_line(x1 + 2, 68, x1 + 9, 68, fill="#6a9955", arrow=tk.LAST)
    canvas.create_text(8, 8, anchor="nw", text="Inference stays research-only",
                       fill="#9cdcfe", font=("Segoe UI", 9, "bold"))
    canvas.create_text(8, 146, anchor="sw",
                       text="No broker access • no execution • deterministic tools validate outputs",
                       fill="#a0a0a0", font=("Segoe UI", 8))
```

This reinforces that the model has no execution authority.
