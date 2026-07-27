---
name: windows-system-monitoring
title: "Windows System Monitoring (psutil / pywin32 / WMI)"
description: >
  Build persistent Windows process/memory/service scanners using psutil, pywin32, and WMI.
  Covers hardening patterns, API quirks, foreground detection, leak heuristics, and
  multi-instance host classification. Load when the user asks to build a tool that
  inspects, monitors, or manages Windows processes, memory, or services.
triggers:
  - "build a process scanner/monitor"
  - "track memory usage on Windows"
  - "enumerate services and classify optional vs essential"
  - "detect duplicate applications or memory leaks programmatically"
  - "inspect Windows processes with psutil prompts"
---

# Windows System Monitoring (psutil / pywin32 / WMI)

## Architecture Pattern

A persistent Windows system monitor follows a **loop: sample → classify → persist → report → sleep** cycle. Keep a ring buffer of per-PID samples so trend detectors (leak, handle growth) have history.

## 1. psutil Process Enumeration — HARDENING

`psutil.process_iter()` can raise per-process. The **critical rule**: wrap every individual field access in its own `try/except`, not just the whole loop body. A single `AccessDenied` or `NoSuchProcess` on one field should not lose the entire process.

```python
for p in psutil.process_iter():
    try:
        with p.oneshot():
            pid = p.pid
            try:
                rss = p.memory_info().rss
            except Exception:
                rss = 0
            try:
                cmd = " ".join(p.cmdline())
            except Exception:
                cmd = ""         # OSError WinError 87 is common
            try:
                nh = p.num_handles()
            except (AttributeError, Exception):
                nh = 0
            try:
                cpu = p.cpu_percent(interval=None)
            except Exception:
                cpu = 0.0
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        continue
```

Known psutil failures on Windows:
- `p.cmdline()` → `OSError: WinError 87` (parameter incorrect) on some system processes
- `p.num_handles()` → `AttributeError` on non-Windows or older psutil
- `p.username()` → `AccessDenied` on SYSTEM processes
- `p.cpu_percent(interval=None)` returns 0.0 on first call (use `p.cpu_times()` delta if you need accurate first-call)

## 2. Windows Service Enumeration — pywin32 + WMI

**pywin32 version problem**: `QueryServiceConfig` returns a **tuple**, not a dict. `startType` is at index 1. `QueryServiceStatus` returns a tuple; `currentState` is at index 1 (4=Running). `SC_STATUS_PROCESS_INFO` may not exist in some pywin32 builds — do NOT rely on it for per-service PID.

**Preferred approach: WMI via win32com** (always available alongside pywin32, more reliable):

```python
import win32com.client
wmi = win32com.client.GetObject("winmgmts:")
for s in wmi.ExecQuery("SELECT Name, DisplayName, State, ProcessId, StartMode FROM Win32_Service"):
    start = {"Auto": 2, "Manual": 3, "Disabled": 4, "Boot": 0, "System": 1}.get(s.StartMode, -1)
    pid = int(s.ProcessId) if s.ProcessId else None
```

**OpenSCManager rights**: use `SC_MANAGER_ENUMERATE_SERVICE | SC_MANAGER_CONNECT` — do NOT request `SC_MANAGER_ALL_ACCESS` (fails on non-admin).

## 3. Foreground / "In Use" Detection

Use `pywin32` + `GetForegroundWindow`:

```python
import win32gui, win32process
def foreground_pid():
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    return pid
```

This lets you decide which process instance the user is actively using (for duplicate-app cleanup).

## 4. Memory Leak Heuristic Design

Process-level leak detection is a **trend heuristic**, not proof. Design:

```
WARMUP: skip processes younger than 120s (still loading)
SAMPLES: need ≥6 samples before judging trend
SLOPE: least-squares linear regression over RSS history
RATE: bytes/sec sustained growth
THRESHOLD: flag if growth_frac > 25% AND rate > 30KB/s AND monotonic
```

```python
def _linear_slope(ys):
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    xm, ym = sum(xs)/n, sum(ys)/n
    num = sum((x-xm)*(y-ym) for x,y in zip(xs, ys))
    den = sum((x-xm)**2 for x in xs)
    return num/den if den else 0.0
```

Handle/thread growth is a cheaper proxy for native alloc leaks:
- Flag if handles grew >200 over the window or threads >50.

## 5. Process Classification

**Multi-instance host processes** (svchost, conhost, RuntimeBroker, etc.) should be excluded from duplicate-app detection — they legitimately run many copies. Maintain a set:

```python
MULTI_INSTANCE_HOSTS = {
    "svchost.exe", "conhost.exe", "csrss.exe", "fontdrvhost.exe",
    "runtimebroker.exe", "dllhost.exe", "taskhostw.exe", "wmiprvse.exe",
    "nvcontainer.exe", "nvdisplay.container.exe", "msedgewebview2.exe",
    "steamwebhelper.exe", "searchhost.exe", "sihost.exe", "chassis.exe",
    "explorer.exe", "audiodg.exe",
}
```

**Extending for real systems**: third-party crash handlers (`crashpad_handler.exe`, `logi_crashpad_handler.exe`, etc.) often run one instance per host app and will appear as "duplicates." Add them to the set when you encounter them — they're legitimate multi-instance, not user-app duplicates.

## 6. Allocation Health Proxy

Windows apps normally reserve 2-5x their working set as virtual address space. The commit/resident ratio alone is noisy. Only flag pathological cases:
- Ratio > 6.0 AND commit > 2GB (soft info, not warn)
- Working set exceeding a user-set baseline by > 25% (real warn)

Deep allocation verification (heap corruption, UAF, double-free) requires AppVerifier pageheap or ASan — not suable from process-level.

## 7. Common Pitfalls

| Pitfall | Fix |
|---------|-----|
| Single bad process kills the whole scan | Wrap every field access in its own try/except |
| `QueryServiceConfig` returns tuple, not dict | Access fields by index, not by key |
| `SC_STATUS_PROCESS_INFO` missing | Use WMI for per-service PID |
| `OpenSCManager` with `ALL_ACCESS` fails | Use `ENUMERATE_SERVICE \| CONNECT` |
| Commit/resident ratio 2-3x flagged as leak | Threshold to >6x or drop the ratio check |
| 106 svchost instances shown as "duplicates" | Exclude MULTI_INSTANCE_HOSTS from group_duplicates |
| `p.cmdline()` raises OSError 87 | Wrap in try/except, default to "" |
| `p.cpu_percent()` returns 0 first call | Pre-call with `interval=None` across all processes first, or use `cpu_times()` delta |

## 8. CLI Architecture (argparse + lazy GUI bridge)

Structure the CLI as a single `build_parser()` that returns an `ArgumentParser` with subparsers. Each subcommand gets `set_defaults(func=cmd_*)`. The `main()` function simply parses and dispatches:

```python
def build_parser():
    ap = argparse.ArgumentParser(prog="mytool")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan", help="one-shot")
    p.set_defaults(func=cmd_scan)
    # ... more subcommands
    return ap

def main():
    args = build_parser().parse_args()
    args.func(args)
```

**Lazy GUI bridge** — keep the GUI module importable but only loaded when requested. The `gui` subcommand uses a wrapper:

```python
def _launch_gui():
    from mytool.gui import main as gui_main
    gui_main()
```

This avoids importing Tkinter (and its DLL load) during CLI-only use.

## 9. Persistent JSON Store

For tools that persist state between runs (policies, baselines, findings), use a thread-safe JSON store:

```python
import json, os, threading
class Store:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._data = {"policies": {}, "baselines": {}, "log": []}
        self._load()
    
    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._data, f, indent=2)
        os.replace(tmp, self.path)
    
    def set_policy(self, key, **kw):
        with self._lock:
            self._data["policies"].setdefault(key, {}).update(kw)
            self._save()
```

Key points:
- Thread lock for concurrent access (scanner thread + GUI thread).
- Atomic write via `write → rename` to prevent corruption.
- Keep the store path under `~/.toolname/` so it's user-local and survives.

## 10. Kill / Stop Safety

**Process kill** — refuse to terminate known critical system processes. Maintain a protected set (svchost, lsass, csrss, wininit, services, etc.). Require `--force` to override:

```python
PROTECTED = {"svchost.exe", "lsass.exe", "csrss.exe", ...}
def safe_kill(pid, force=False):
    p = psutil.Process(pid)
    if p.name() in PROTECTED and not force:
        return False, "protected"
    p.terminate()
    return True, "terminated"
```

**Service stop** — use WMI `StopService()`. Protect essential services (RPCSS, LSASS, Power, PlugPlay, etc.):

```python
def stop_service(name, force=False):
    info = find_service(name)
    if info.essential and not force:
        return False, "refusing essential service"
    wmi = win32com.client.GetObject("winmgmts:")
    for s in wmi.ExecQuery(f"SELECT * FROM Win32_Service WHERE Name='{name}'"):
        ret = s.StopService()
        return ret[0] == 0, f"returned {ret[0]}"
```

## 11. System Tray / Tkinter GUI

For a lightweight Windows dashboard (no extra deps), combine **Tkinter** + **pywin32 Shell_NotifyIcon**:

### Near-black theme
```
BG      = "#0d1117"   # background
SURFACE = "#161b22"   # card/panel
ACCENT  = "#ff6b35"   # orange accent
TEXT    = "#e6edf3"   # primary text
SUBTEXT = "#8b949e"   # secondary
CRIT    = "#f85149"   # red
WARN    = "#d29922"   # yellow
GREEN   = "#3fb950"   # success
BTN     = "#21262d"   # button bg
```

### Background scan thread
The scanner runs in a `threading.Thread` daemon; findings go into a `queue.Queue`. The GUI polls the queue via `root.after(1000, poll_queue)`:

```python
self._q = queue.Queue()
def _scan_loop(self):
    while self._running:
        views = scanner.sample()
        findings = run_detectors(views)
        self._q.put({"views": views, "findings": findings})
        time.sleep(interval)
def _poll_queue(self):
    try:
        while True:
            data = self._q.get_nowait()
            # refresh treeviews, labels, etc.
    except queue.Empty:
        pass
    self.root.after(1000, self._poll_queue)
```

### Tkinter ↔ pywin32 bridge for system tray
Get the window's HWND via `self.root.winfo_id()` (returns a valid Windows HWND on Windows). Register a custom window message and hook the window proc:

```python
import win32gui, win32api, win32con

hwnd = self.root.winfo_id()
WM_TRAY = win32api.RegisterWindowMessage(f"tray_msg_{id(self)}")

def wndproc(h, msg, w, l):
    if msg == WM_TRAY:
        if l == win32con.WM_LBUTTONDBLCLK:
            self.root.deiconify()    # restore window
        elif l == win32con.WM_RBUTTONUP:
            # show context menu
    return win32gui.CallWindowProc(old_proc, h, msg, w, l)

old_proc = win32gui.SetWindowLong(hwnd, win32con.GWL_WNDPROC, wndproc)

nid = (hwnd, 0,
       win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
       WM_TRAY,
       hicon,   # icon handle (use LoadIcon or a custom resource)
       "tooltip text")
win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
```

**Close-to-tray**: override `WM_DELETE_WINDOW` → `self.root.withdraw()`. On tray double-click → `self.root.deiconify()`.

**Context menu**: use `win32gui.TrackPopupMenu`. Wire menu item callbacks via `root.after()` since you're inside the window proc.

### Card-style layouts with LabelFrame (avoid `pad=` pitfall)

When grouping duplicate apps or services, `tk.LabelFrame` with `bg=`/`fg=` works well for card-style layouts. **Crucial**: `LabelFrame` does NOT accept a `pad=` option — it silently produces `_tkinter.TclError: unknown option "-pad"`. Use `padx=` and `pady=` instead:

```python
# OK
card = tk.LabelFrame(parent, text="Group Name", bg=SURFACE, fg=ACCENT, padx=6, pady=3)

# WRONG — raises TclError
card = tk.LabelFrame(parent, text="Group Name", pad=6)
```

When building per-group cards in the Dupes tab, pack a `tk.Frame` row per member inside the card, with a "Kill" button for idle instances:

```python
card = tk.LabelFrame(f, text=f" {exe_name} ({len(members)}×) ", ...)
card.pack(fill=tk.X, padx=4, pady=2)
for m in members:
    row = tk.Frame(card, bg=SURFACE)
    row.pack(fill=tk.X, padx=4, pady=1)
    tk.Label(row, text=f"  PID {m.pid}  {m.name}  started ...", ...).pack(side=tk.LEFT)
    if m.pid != active_pid:
        ttk.Button(row, text="Kill", style="Danger.TButton", width=5).pack(side=tk.RIGHT)
```

### Tab structure pattern (TTK Notebook)
```python
nb = ttk.Notebook(root)
# Each tab is a ttk.Frame with a Treeview + action buttons
leaks_frame = ttk.Frame(nb)
nb.add(leaks_frame, text="  Leaks  ")
# ... populate with Treeview, buttons bound to refresh
```

Color-code findings using Treeview tags:
```python
tv.tag_configure("crit", foreground=CRIT)
tv.tag_configure("warn", foreground=WARN)
tv.insert("", tk.END, values=(...), tags=("crit",))
```

### When to build the GUI
Build the CLI + engine first, test end-to-end against live data, then add the GUI as a thin viewer. This keeps the CLI testable and the GUI a pure render layer over the same detector/scan pipeline.

See `references/tkinter-system-tray.md` for the full Shell_NotifyIcon struct and window-proc hook.

## 12. Resource Monitor: Diagnose Hard Faults Correctly

When a user reports Windows **Hard Faults/sec**, use Resource Monitor (`resmon.exe`) rather than treating `\\Process(*)\\Page Faults/sec` as equivalent. The Performance counter includes soft faults and cannot attribute **hard** faults cleanly to an individual process.

1. Open Resource Monitor and inspect the expanded **Memory** section on **Overview**, or the **Memory** tab.
2. Observe it for at least 30–60 seconds; one sample can catch routine cold-page loading.
3. Record the Memory header's total **Hard Faults/sec**, `% Used Physical Memory`, the per-process **Hard Faults/sec** column, Disk's highest active time, and the right-side hard-fault graph.
4. Interpret the signals together:
   - `0` or occasional low, brief hard faults with ample available RAM and low disk active time are normal page-ins. Do not recommend pagefile changes or RAM replacement.
   - Sustained high hard faults plus rising physical-memory use and busy/slow disk warrants investigation of the top process, its working-set growth, commit pressure, and storage latency.
   - A hard fault is a disk-backed page-in (executable, mapped file, standby list, or pagefile), **not proof of defective physical RAM**.
5. If the native UI is inaccessible, use `\\Memory\\Pages Input/sec` and `\\Memory\\Page Reads/sec` for overall paging pressure, but explicitly label them as system-wide rather than per-process hard-fault metrics.

## 13. Running PowerShell from the Hermes git-bash terminal (host quirks)

On this Windows host the `terminal` tool is MSYS bash, and Windows admin work is done by invoking `powershell.exe -NoProfile -Command '...'`. Three recurring traps:

| Trap | Symptom | Fix |
|------|---------|-----|
| Bash expands `$var` inside double quotes | `foreach( in ...)` / `=(Get-ItemProperty...)` parse errors — bash ate `$_`, `$pid_`, `$rdp` | ALWAYS wrap the PowerShell command in **single quotes**: `powershell.exe -NoProfile -Command '...'`. Use double quotes for PS strings inside |
| `Out-File` default encoding (PS 5.1) | Log flagged "binary" by read_file; looks like `- - s r v 2` with NULs | Read elevated-job logs back with `Get-Content` in a terminal call, not read_file. `-Encoding ascii` doesn't fully save you when piping `sc.exe` output |
| Shell is NOT elevated | `Stop-Service`/`Set-Service` → "Access is denied" | Elevation pattern below |

**Elevation pattern (user must approve a UAC prompt on-screen):**

1. Write the script with write_file; have it log results to a file.
2. `powershell.exe -NoProfile -Command 'Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File C:\Users\<user>\job.ps1" -Wait'`
3. Read the log back with `Get-Content`; delete temp `.ps1` + `.log` when done.

Warn the user a UAC prompt is coming before launching. Never leave staged files behind.

**WMI filter quoting from bash**: `-Filter "Name='X'"` gets mangled by nested quotes; prefer `Get-Service -Name X` / pipeline `Where-Object` over `Get-CimInstance -Filter`.

## 14. Verification

Run a one-shot `scan` to confirm process enumeration works. Run `services` to confirm WMI service enumeration. For leak detection, run `watch` for at least 120s (warmup) to see if any trend findings appear. Test duplicate detection by running two instances of a test app.

For Tkinter GUI: launch with `timeout 3 tool gui` — exit code 124 (killed by timeout) confirms the window opened and the event loop ran without crashing. No error output means clean launch.