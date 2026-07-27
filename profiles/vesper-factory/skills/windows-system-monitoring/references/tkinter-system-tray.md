# Tkinter + pywin32 System Tray Pattern (Windows)

Verified against Python 3.11.15, pywin32 306, on Windows 10.

## Goal

A Tkinter window that hides to the system tray when closed, restores on double-click, and shows a right-click context menu. No extra deps — uses `win32gui.Shell_NotifyIcon` and the window-proc hook.

## Getting the HWND

On Windows, `tkinter.Tk.winfo_id()` returns a valid Windows `HWND`. This is the handle you pass to `Shell_NotifyIcon`:

```python
hwnd = self.root.winfo_id()
```

## Registering a custom window message

Each tray icon needs a unique callback message ID. Use `win32api.RegisterWindowMessage`:

```python
import win32api, win32gui, win32con
WM_TRAY = win32api.RegisterWindowMessage(f"tray_msg_{id(self)}")
```

## Hooking the window procedure

Replace the Tk window's default window proc. The new proc must call the old one for unhandled messages:

```python
def wndproc(h, msg, w, l):
    if msg == WM_TRAY:
        if l == win32con.WM_LBUTTONDBLCLK:
            self.root.deiconify()
            self.root.lift()
        elif l == win32con.WM_RBUTTONUP:
            _show_tray_menu(self, h)
    return win32gui.CallWindowProc(self._old_proc, h, msg, w, l)

self._old_proc = win32gui.SetWindowLong(
    hwnd, win32con.GWL_WNDPROC, wndproc
)
```

## Creating the tray icon

`Shell_NotifyIcon(NIM_ADD, nid)` where `nid` is a tuple:

```python
# Load a default icon (or use your own via LoadImage)
hicon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
nid = (
    hwnd,                            # HWND that receives callback messages
    0,                               # icon ID (0 = first/only)
    win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,  # flags
    WM_TRAY,                         # callback message ID
    hicon,                           # icon handle
    "tooltip text"                   # tooltip string
)
win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
```

**NIF flags** (from `win32gui`):
- `NIF_MESSAGE` — the icon sends callback messages
- `NIF_ICON` — the icon has a visible icon
- `NIF_TIP` — the icon has a tooltip
- `NIF_INFO` — the icon can show a balloon notification

## Context menu

Use `win32gui.CreatePopupMenu` + `win32gui.AppendMenu` + `win32gui.TrackPopupMenu` inside the right-click handler. Wire menu commands via `root.after` since you're in the window proc (not the Tk event loop):

```python
def _show_tray_menu(self, hwnd):
    menu = win32gui.CreatePopupMenu()
    win32gui.AppendMenu(menu, win32con.MF_STRING, 1, "Show")
    win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, None)
    win32gui.AppendMenu(menu, win32con.MF_STRING, 2, "Quit")
    # TrackPopupMenu blocks until the user dismisses it
    # Use root.after to handle the selection
    self.root.after(0, lambda: self._handle_menu(hwnd, menu))
    win32gui.TrackPopupMenu(menu, win32con.TPM_LEFTALIGN, 0, 0, 0, hwnd, None)

def _handle_menu(self, hwnd, menu):
    cmd = win32gui.GetMenuDefaultItem(menu, False, 0)
    if cmd == 1:
        self.root.deiconify()
    elif cmd == 2:
        self._remove_tray()
        self.root.quit()
```

## Close-to-tray behavior

Override the window close button (`WM_DELETE_WINDOW` protocol):

```python
self.root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)

def _hide_to_tray(self):
    self.root.withdraw()          # hide the window
    # Shell_NotifyIcon(NIM_ADD) already called once; the icon persists
```

## Removing the icon on quit

```python
def _remove_tray(self):
    try:
        win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, self._tray_icon)
    except Exception:
        pass
```

## Complete lifecycle

1. GUI starts → `Shell_NotifyIcon(NIM_ADD)` creates tray icon
2. User clicks X → `withdraw()` hides window, icon stays
3. User double-clicks tray → `deiconify()` + `lift()` restores
4. User right-clicks tray → "Show" (restore) or "Quit" (remove icon + `root.quit()`)
5. On `root.quit()` → `_remove_tray()` deletes the icon

## Known pitfalls

| Pitfall | Fix |
|---------|------|
| Tray icon shows but doesn't respond to clicks | Register the window message with `RegisterWindowMessage` (not `WM_USER + N`), and ensure `NIF_MESSAGE` flag is set |
| `SetWindowLong` fails with "access denied" | The window must be mapped (call `root.update()` before hooking) |
| Icon disappears after explorer restart | Listen for `TaskbarCreated` message and re-add the icon |
| `TrackPopupMenu` blocks the Tk event loop | It's called from the window proc, not the Tk loop — this is fine |
| `Shell_NotifyIcon` raises `TypeError` | The tuple format changed between pywin32 versions. The `(hwnd, id, flags, callback, hicon, tip)` format is stable across pywin32 304–306 |
| `LoadIcon(0, IDI_APPLICATION)` returns a generic icon | Use `LoadImage(0, path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)` for a custom icon |
| `tk.LabelFrame(... pad=6)` raises `TclError: unknown option "-pad"` | `LabelFrame` does not support `pad=`. Use `padx=` and `pady=` instead |
| `tk.LabelFrame` cards look cramped with no padding | Always pass `padx=6, pady=3` to `LabelFrame` for visual breathing room on the card border |