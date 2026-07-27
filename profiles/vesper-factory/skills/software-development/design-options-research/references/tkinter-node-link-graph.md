# Tkinter Node-Link Graph Recipe

A lightweight, dark-themed node-link graph using `tk.Canvas`. Useful for showing a pipeline, knowledge graph, or training progression where nodes light up as stages complete.

## When to use

- The user wants a graph view rather than a linear progress bar.
- You need to show relationships (edges) between conceptual stages (nodes).
- The display must update as status changes without redrawing the whole window.

## Recipe

```python
import math
import tkinter as tk
from typing import Any


def draw_graph(
    canvas: tk.Canvas,
    center: dict[str, Any],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, str]],
    caption: str,
) -> None:
    canvas.delete("all")
    width = max(canvas.winfo_width(), 320)
    height = max(canvas.winfo_height(), 156)

    colors = {
        "complete": {"node": "#4ec9b0", "edge": "#4ec9b0", "ring": "#2d6a4f"},
        "active": {"node": "#007acc", "edge": "#007acc", "ring": "#1a4c7a"},
        "pending": {"node": "#3c3c3c", "edge": "#3c3c3c", "ring": "#2a2a2a"},
    }

    center_x, center_y = width // 2, height // 2 - 6
    node_radius = 7
    center_radius = 12

    # Position satellites in a ring
    positions: dict[str, tuple[float, float]] = {}
    for index, node in enumerate(nodes):
        angle = -math.pi / 2 + 2 * math.pi * index / len(nodes)
        distance = min(width, height) * 0.33
        positions[node["id"]] = (
            center_x + math.cos(angle) * distance,
            center_y + math.sin(angle) * distance,
        )
    positions["center"] = (center_x, center_y)

    # Draw edges first (behind nodes)
    for edge in edges:
        x0, y0 = positions[edge["source"]]
        x1, y1 = positions[edge["target"]]
        target_status = next(
            (n["status"] for n in nodes if n["id"] == edge["target"]), "pending"
        )
        canvas.create_line(
            x0, y0, x1, y1,
            fill=colors[target_status]["edge"],
            width=2,
            arrow=tk.LAST,
            arrowshape=(7, 9, 3),
        )

    # Draw satellite nodes with status rings
    for node in nodes:
        x, y = positions[node["id"]]
        style = colors[node["status"]]
        canvas.create_oval(
            x - node_radius - 3, y - node_radius - 3,
            x + node_radius + 3, y + node_radius + 3,
            fill=style["ring"], outline="",
        )
        canvas.create_oval(
            x - node_radius, y - node_radius,
            x + node_radius, y + node_radius,
            fill=style["node"], outline="",
        )
        canvas.create_text(
            x, y + node_radius + 13,
            text=node["label"], fill="#d4d4d4",
            font=("Segoe UI", 8, "bold"),
        )
        canvas.create_text(
            x, y + node_radius + 27,
            text=node.get("detail", ""), fill="#a0a0a0",
            font=("Segoe UI", 7),
        )

    # Draw center hub
    style = colors[center["status"]]
    canvas.create_oval(
        center_x - center_radius - 3, center_y - center_radius - 3,
        center_x + center_radius + 3, center_y + center_radius + 3,
        fill=style["ring"], outline="",
    )
    canvas.create_oval(
        center_x - center_radius, center_y - center_radius,
        center_x + center_radius, center_y + center_radius,
        fill=style["node"], outline="",
    )
    canvas.create_text(
        center_x, center_y + center_radius + 16,
        text=center["label"], fill="#d4d4d4",
        font=("Segoe UI", 8, "bold"),
    )

    # Caption and legend
    canvas.create_text(
        8, 8, anchor="nw", text="Pipeline",
        fill="#9cdcfe", font=("Segoe UI", 9, "bold"),
    )
    canvas.create_text(
        8, height - 8, anchor="sw", text=caption,
        fill="#a0a0a0", font=("Segoe UI", 8),
    )
```

## Expected node shape

```python
nodes = [
    {"id": "dataset", "label": "Dataset", "status": "complete", "detail": "240 train"},
    {"id": "lora", "label": "LoRA", "status": "active", "detail": "training"},
    {"id": "eval", "label": "Eval", "status": "pending", "detail": "pending"},
]
edges = [
    {"source": "dataset", "target": "lora"},
    {"source": "lora", "target": "eval"},
]
center = {"label": "run-001", "status": "active"}
```

## Tips

- Bind `<Configure>` on the canvas to redraw on resize.
- Keep node `status` in `{"pending", "active", "complete"}`.
- Use `detail` for live numbers (step count, loss, pass rate).
- Position nodes in a ring for a knowledge-graph feel; use a horizontal pipeline layout when the sequence is strictly linear.
- Draw edges before nodes so arrowheads do not get clipped by node circles.
- Status rings help nodes read clearly against a dark canvas.

## Common pitfalls

- **Labels overlap edges.** Leave enough margin between the node ring and the label.
- **Too many nodes.** A ring of more than 8–10 nodes becomes crowded; split into groups or use a scrollable/expandable graph.
- **No caption.** The graph shows structure; the caption interprets current state.
- **Static center.** Update the center label and status to reflect the active run or pipeline instance.
- **Rebuilding on every poll.** Redraw only when the underlying graph state changes to avoid flicker.
