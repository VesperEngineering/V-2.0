# Canvas Node-Link Graph for Training Progression

A Tkinter `Canvas` can render an Obsidian-style node-link graph that shows
training stages growing and lighting up as they complete. This is more
informative than a static `BASE → LoRA → EVAL` text line.

## Graph model

Nodes:
- Center hub: run ID.
- Satellites (clockwise from top): Dataset, Base model, LoRA adapter,
  Loss curve, Holdout eval, Benchmark eval, Report.

Edges:
- Dataset → LoRA
- Base model → LoRA
- LoRA → Loss curve
- Loss curve → Holdout eval
- Loss curve → Benchmark eval
- Holdout eval → Report
- Benchmark eval → Report

Each node carries a status:
- `pending` — gray
- `active` — blue
- `complete` — green

## Generating graph state

```python
from __future__ import annotations

from typing import Any


def training_graph_state(
    current: dict[str, Any] | None,
    latest_report: dict[str, Any] | None,
    latest_evaluation: dict[str, Any] | None,
) -> dict[str, Any]:
    status = current.get("status") if current is not None else None
    phase = current.get("phase", "").lower() if current is not None else ""
    run_id = current.get("run_id") if current is not None else None

    report = latest_report if latest_report is not None and latest_report.get("run_id") == run_id else None
    eval_data = latest_evaluation if latest_evaluation is not None and latest_evaluation.get("run_id") == run_id else None

    train_count = report.get("train_count") if report is not None else None
    holdout_count = report.get("holdout_count") if report is not None else None
    final_loss = report.get("train_loss_final") if report is not None else None

    adapter_passed = None
    total = None
    if eval_data is not None:
        adapter_summary = eval_data.get("adapter", {}).get("summary", {})
        adapter_passed = adapter_summary.get("passed")
        total = adapter_summary.get("count")

    is_running = status == "RUNNING"
    is_evaluating = status == "EVALUATING"
    is_complete = status == "COMPLETE" or "completed" in phase

    def stage_status(complete_condition: bool, active_condition: bool) -> str:
        if complete_condition:
            return "complete"
        if active_condition:
            return "active"
        return "pending"

    nodes = [
        {"id": "dataset", "label": "Dataset", "status": stage_status(is_running or is_evaluating or is_complete, False), "detail": f"{train_count} train" if train_count is not None else "awaiting admission"},
        {"id": "base", "label": "Base model", "status": stage_status(is_running or is_evaluating or is_complete, False), "detail": report.get("model", "Qwen 1.5B") if report is not None else "Qwen 1.5B"},
        {"id": "lora", "label": "LoRA adapter", "status": stage_status(is_evaluating or is_complete, is_running), "detail": "training" if is_running else ("saved" if is_complete or is_evaluating else "not started")},
        {"id": "loss", "label": "Loss curve", "status": stage_status(is_evaluating or is_complete, is_running), "detail": f"loss {final_loss:.3f}" if final_loss is not None else "no data"},
        {"id": "holdout", "label": "Holdout eval", "status": stage_status(is_complete, is_evaluating), "detail": f"adapter {adapter_passed}/{holdout_count}" if adapter_passed is not None and holdout_count is not None else "pending"},
        {"id": "benchmark", "label": "Benchmark eval", "status": stage_status(is_complete, is_evaluating), "detail": f"adapter {adapter_passed}/{total}" if adapter_passed is not None and total is not None else "pending"},
        {"id": "report", "label": "Report", "status": stage_status(is_complete, False), "detail": run_id if run_id is not None else "—"},
    ]

    edges = [
        {"source": "dataset", "target": "lora"},
        {"source": "base", "target": "lora"},
        {"source": "lora", "target": "loss"},
        {"source": "loss", "target": "holdout"},
        {"source": "loss", "target": "benchmark"},
        {"source": "holdout", "target": "report"},
        {"source": "benchmark", "target": "report"},
    ]

    if is_running:
        caption = "Training is active. The LoRA node is updating; evaluation nodes are pending."
    elif is_evaluating:
        caption = "Evaluation is running. Comparing base model and adapter on held-out cases."
    elif is_complete:
        caption = f"Run {run_id} complete. Review the holdout and benchmark results before promotion."
    else:
        caption = "No active run. Dataset admission is the first gate."

    return {
        "center": {"label": run_id if run_id is not None else "No run", "status": "active" if is_running else ("complete" if is_complete else "pending")},
        "nodes": nodes,
        "edges": edges,
        "caption": caption,
    }
```

## Rendering on a Tkinter Canvas

```python
import math
import tkinter as tk
from typing import Any


def draw_training_graph(canvas: tk.Canvas, graph: dict[str, Any]) -> None:
    canvas.delete("all")
    width = max(canvas.winfo_width(), 320)
    height = max(canvas.winfo_height(), 156)

    colors = {
        "complete": {"node": "#4ec9b0", "text": "#1e1e1e", "edge": "#4ec9b0"},
        "active": {"node": "#007acc", "text": "#ffffff", "edge": "#007acc"},
        "pending": {"node": "#3c3c3c", "text": "#808080", "edge": "#3c3c3c"},
    }

    center_x, center_y = width // 2, height // 2 - 8
    node_radius = 8

    node_positions: dict[str, tuple[float, float]] = {}
    satellites = [node for node in graph["nodes"] if node["id"] != "center"]
    for index, node in enumerate(satellites):
        angle = -math.pi / 2 + 2 * math.pi * index / len(satellites)
        distance = min(width, height) * 0.34
        node_positions[node["id"]] = (
            center_x + math.cos(angle) * distance,
            center_y + math.sin(angle) * distance,
        )
    node_positions["center"] = (center_x, center_y)

    # edges behind nodes
    for edge in graph["edges"]:
        x0, y0 = node_positions[edge["source"]]
        x1, y1 = node_positions[edge["target"]]
        target_status = next((node["status"] for node in graph["nodes"] if node["id"] == edge["target"]), "pending")
        canvas.create_line(x0, y0, x1, y1, fill=colors[target_status]["edge"], width=2, arrow=tk.LAST, arrowshape=(8, 10, 3))

    # center hub
    center = graph["center"]
    style = colors[center["status"]]
    canvas.create_oval(
        center_x - node_radius - 2, center_y - node_radius - 2,
        center_x + node_radius + 2, center_y + node_radius + 2,
        fill=style["node"], outline="",
    )
    canvas.create_text(center_x, center_y + node_radius + 16, text=center["label"], fill="#d4d4d4", font=("Segoe UI", 8, "bold"))

    # satellites
    for node in satellites:
        x, y = node_positions[node["id"]]
        style = colors[node["status"]]
        canvas.create_oval(
            x - node_radius, y - node_radius,
            x + node_radius, y + node_radius,
            fill=style["node"], outline="",
        )
        canvas.create_text(x, y + node_radius + 12, text=node["label"], fill="#d4d4d4", font=("Segoe UI", 8, "bold"))
        canvas.create_text(x, y + node_radius + 26, text=node["detail"], fill="#a0a0a0", font=("Segoe UI", 7))

    canvas.create_text(8, 8, anchor="nw", text="Training pipeline", fill="#9cdcfe", font=("Segoe UI", 9, "bold"))
    canvas.create_text(8, height - 8, anchor="sw", text=graph["caption"], fill="#a0a0a0", font=("Segoe UI", 8))
```

Bind `<Configure>` on the Canvas to redraw on resize:

```python
canvas.bind("<Configure>", lambda _event: draw_training_graph(canvas, graph))
```

## Testing

Unit-test the graph-state function, not the Canvas drawing:

```python
def test_training_graph_state_builds_pipeline() -> None:
    graph = training_graph_state(
        {"status": "COMPLETE", "run_id": "qra-test", "phase": "comparison completed"},
        {"run_id": "qra-test", "train_count": 240, "train_loss_final": 0.806},
        {"run_id": "qra-test", "adapter": {"summary": {"passed": 2, "count": 50}}},
    )
    assert graph["center"]["label"] == "qra-test"
    assert {node["id"] for node in graph["nodes"]} == {"dataset", "base", "lora", "loss", "holdout", "benchmark", "report"}
```

## Variations

- Add a sparkline inside the "Loss curve" node by drawing a tiny polyline.
- Add a pulsing ring around the active node by redrawing with a larger,
  partially transparent oval on a timer.
- Use curved edges (create_line with `smooth=True`) for a more organic
  graph look.
