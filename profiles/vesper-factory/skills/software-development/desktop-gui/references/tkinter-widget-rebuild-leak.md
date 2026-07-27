# Tkinter widget-rebuild memory leak (memwatch case study)

A real-world case: **memwatch v0.1.0** — a lightweight Tkinter process/memory/service scanner built on Windows with Python 3.11, psutil, pywin32, and win32com.

## The leak

The Dupes tab refreshed every 5 seconds by destroying + recreating `tk.LabelFrame` + `tk.Label` + `ttk.Button` widgets for every duplicate instance. After 150 samples (12.5 minutes):

```
crit | 21180 | python.exe | Possible memory leak: +100.7% over 150 samples
Handles: 590 → 614+ (continuing growth)
```

RSS grew from ~39 MB to ~79 MB. The growth was monotonic and bounded only by the number of duplicate instances, which varied.

## Root cause

```python
# BAD: this was in _refresh_dupes
def _refresh_dupes(self):
    f = self._dupes_frame
    for w in f.winfo_children():
        w.destroy()          # Tkinter doesn't fully release old widget trees
    for exe, members in sorted(groups):
        card = tk.LabelFrame(f, ...)   # new widget tree every refresh
        for m in members:
            row = tk.Frame(card)
            lbl = tk.Label(row, ...)
            btn = ttk.Button(row, text="Kill", ...)
```

Every refresh created N new widgets without freeing the old ones' memory.

## Fix

Replace the LabelFrame-per-row pattern with a **Treeview** (shared internal cells, no widget accumulation):

```python
def _build_dupes_tab(self, nb):
    f = ttk.Frame(nb)
    cols = ("flag", "pid", "exe", "name", "started")
    tv = ttk.Treeview(f, columns=cols, show="headings", height=12)
    # ... configure columns ...
    tv.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4,0))
    self._dupes_tv = tv
    # Single "Kill Selected" button below treeview
    ttk.Button(f, text="Kill Selected", command=self._kill_selected_dupe,
               style="Danger.TButton").pack(side=tk.RIGHT)

def _refresh_dupes(self):
    tv = self._dupes_tv
    tv.delete(*tv.get_children())  # clears data only, no widget leak
    for exe, members in sorted(groups):
        for m in members:
            tv.insert("", tk.END, values=(flag, m.pid, exe_short, ...), tags=(...))
```

## Self-PID skip

The tool also flagged itself because the Python allocator doesn't return pages to the OS. Fix:

```python
import os
self_pid = os.getpid()
for v in views:
    if v.pid == self_pid:
        continue
    # ... detectors ...
```

Apply in every detection loop (CLI `cmd_watch`/`cmd_leaks`, GUI `_run_detectors`).

## Other patterns from memwatch

### Process memory leak detection (psutil)

```python
rss = [float(s.rss) for s in proc.samples]
growth = (rss[-1] - rss[0]) / rss[0]        # growth fraction
slope = linear_slope(rss)                    # bytes per sample
rate = slope / interval                      # bytes/sec
# Flag if: growth > 25% AND rate > 30KB/s AND >70% consecutive increases
```

### Handle leak proxy

```python
h = [s.num_handles for s in proc.samples]
if h[-1] - h[0] >= 200:                     # handles gained over window
    # possible native alloc leak
```

### Duplicate application detection

```python
groups = defaultdict(list)
for v in views:
    bare = v.name.lower()
    if bare in MULTI_INSTANCE_HOSTS:         # skip svchost, conhost, ...
        continue
    groups[v.exe].append(v)
return {k: g for k, g in groups.items() if len(g) > 1}
```

### WMI service enumeration (pywin32)

```python
import win32com.client
wmi = win32com.client.GetObject("winmgmts:")
for s in wmi.ExecQuery(
    "SELECT Name, DisplayName, State, ProcessId, StartMode FROM Win32_Service"
):
    start = {"Auto": 2, "Manual": 3, "Disabled": 4}.get(s.StartMode, -1)
    optional = start in (3, 4)
    essential = s.Name in {"RPCSS", "DcomLaunch", "LSASS", ...} or start in (0, 1)
```

### System tray (pywin32 Shell_NotifyIcon)

```python
import win32gui, win32con, win32api
WM_TRAY = win32api.RegisterWindowMessage("tray_<unique>")
nid = (hwnd, 0,
       win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
       WM_TRAY, hicon, "tooltip")
win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
# In window proc: msg == WM_TRAY → lParam == WM_LBUTTONDBLCLK → restore
```
