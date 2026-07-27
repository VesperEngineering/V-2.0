# Windows Tk Background Capture and Canvas Interaction Probes

Use this when a native Tkinter window must be visually or interactively verified without stealing foreground focus.

## Why screen-region capture is insufficient

`PIL.ImageGrab.grab(bbox=...)` captures the pixels currently composited at that screen rectangle. If another window occludes the Tk window, the image shows the occluder even when the target HWND and rectangle are correct. `SetForegroundWindow` is also not reliable evidence: Windows may reject foreground activation, and it disrupts the user.

For an occlusion-independent capture, identify the exact titled HWND and render that window with `PrintWindow`.

## HWND-specific `PrintWindow` capture

Use `EnumWindows` plus an exact title/version match, then capture with pywin32 device contexts. Pass flag `2` (`PW_RENDERFULLCONTENT`) and record whether `PrintWindow` returned success.

```python
import ctypes
from pathlib import Path

import win32gui
import win32ui
from PIL import Image

user32 = ctypes.windll.user32
hwnd = ...  # exact visible HWND found via EnumWindows
left, top, right, bottom = win32gui.GetWindowRect(hwnd)
width, height = right - left, bottom - top
window_dc = win32gui.GetWindowDC(hwnd)
source_dc = win32ui.CreateDCFromHandle(window_dc)
memory_dc = source_dc.CreateCompatibleDC()
bitmap = win32ui.CreateBitmap()

try:
    bitmap.CreateCompatibleBitmap(source_dc, width, height)
    memory_dc.SelectObject(bitmap)
    rendered = user32.PrintWindow(hwnd, memory_dc.GetSafeHdc(), 2)
    if not rendered:
        raise RuntimeError("PrintWindow did not render the target HWND")
    info = bitmap.GetInfo()
    bits = bitmap.GetBitmapBits(True)
    image = Image.frombuffer(
        "RGB",
        (info["bmWidth"], info["bmHeight"]),
        bits,
        "raw",
        "BGRX",
        0,
        1,
    )
    image.save(Path("window-capture.png"))
finally:
    win32gui.DeleteObject(bitmap.GetHandle())
    memory_dc.DeleteDC()
    source_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, window_dc)
```

Inspect the resulting image rather than treating a successful API return as visual acceptance. Verify title/version, intended panes, authoritative values, clipping, scrollbars, and empty/unreadable regions.

## Verifying Canvas item bindings without foreground input

A `Canvas.tag_bind()` callback depends on Tk's mapped-item `current` tag. A withdrawn root has no mapped item under the pointer, so `event_generate("<Button-1>")` can silently fail even when the binding is correct. Sending `WM_LBUTTONDOWN` to the top-level HWND is also weak evidence because it may not reproduce Tk's internal item hit-testing.

Use a fully mapped but transparent verification window:

1. Inject or monkeypatch snapshot loading before constructing the app so the probe cannot launch real subprocesses or network work.
2. Construct the real app and set `root.attributes("-alpha", 0.0)` instead of calling `withdraw()`.
3. Populate a deterministic, authoritative-shaped snapshot and render it.
4. Call `update_idletasks()` and `update()` so geometry and Canvas hit-testing exist.
5. Compute the target point from the same layout/projection used by production drawing.
6. Generate `<Motion>` at the target first, then `<Button-1>`; update Tk again.
7. Assert the durable selection field and user-visible detail text, not merely callback execution.
8. Close the app in `finally` and remove the external temporary probe.

```python
app = AppClass()
app.attributes("-alpha", 0.0)
try:
    app.install_snapshot(snapshot)
    app.update_idletasks()
    app.update()
    canvas.event_generate("<Motion>", x=x, y=y)
    canvas.event_generate("<Button-1>", x=x, y=y)
    app.update_idletasks()
    app.update()
    assert app.selected_node_id == expected_id
    assert expected_detail in app.detail_text.get()
finally:
    app.destroy()
```

## Acceptance ladder

For a native Tk dashboard change, keep the evidence layers distinct:

1. Pure projection tests (RED/GREEN) for receipt/state truth.
2. Syntax, targeted tests, lint, and type checks.
3. Real application smoke path using the same snapshot loader as production.
4. Exact-HWND `PrintWindow` visual inspection.
5. Transparent mapped-window Canvas interaction probe.
6. Close only verification processes; remove external probes/screenshots/basetemps.

Never claim interaction success from a failed or ambiguous click attempt. State why the first probe was invalid, improve the probe, and require an observable state change before acceptance.
