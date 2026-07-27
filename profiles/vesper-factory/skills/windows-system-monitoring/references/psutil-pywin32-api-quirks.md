# psutil / pywin32 / WMI API Quirks (Windows)

Verified against Python 3.11.15, psutil 7.2.2, pywin32 306, on Windows 10.

## psutil

### `p.cmdline()` → OSError WinError 87
On some processes (system processes, certain protected processes), `ReadProcessMemory`
fails with "The parameter is incorrect." This is not `AccessDenied` — it's an `OSError`
with WinError 87. Wrap in `try/except Exception` and default to `""`.

### `p.cpu_percent(interval=None)` returns 0.0 on first call
The first call accumulates per-process CPU times but doesn't have a delta to compute
a percentage from. Use `p.cpu_times()` and compute your own delta:

```python
prev = cpu_cache.get(pid)
now = time.time()
if prev:
    dt = now - prev[0]
    dc = (p.user + p.system) - (prev[1].user + prev[1].system)
    pct = (dc / dt) * 100 if dt > 0 else 0.0
else:
    pct = 0.0
cpu_cache[pid] = (now, p.cpu_times())
```

### `p.num_handles()` only on Windows
Raises `AttributeError` on non-Windows or older psutil. Wrap in `try/except (AttributeError, Exception)`.

### `p.oneshot()` context manager
Use `with p.oneshot():` when accessing multiple fields of the same process. It caches
the process info so each field access doesn't make a separate syscall.

## pywin32 — Service Control Manager

### `QueryServiceConfig` returns tuple, not dict
In pywin32 306, `QueryServiceConfig(h)` returns a 9-tuple:
```
(serviceType, startType, errorControl, binaryPath, loadOrderGroup,
 tagId, dependencies, serviceStartName, displayName)
```
Access `startType` via `config[1]`, not `config["startType"]`.

### `QueryServiceStatus` returns tuple, not dict
Returns a 7-tuple:
```
(serviceType, currentState, controlsAccepted, win32ExitCode,
 serviceSpecificExitCode, checkPoint, waitHint)
```
Constants: SERVICE_STOPPED=1, START_PENDING=2, STOP_PENDING=3, RUNNING=4,
CONTINUE_PENDING=5, PAUSE_PENDING=6, PAUSED=7.

### `SC_STATUS_PROCESS_INFO` may not exist
Some pywin32 builds lack this constant. `QueryServiceStatusEx()` with it will
raise `AttributeError`. Use WMI instead for per-service PID.

### `OpenSCManager` rights
```python
# This works on non-admin:
sc = win32service.OpenSCManager(
    None, None, win32service.SC_MANAGER_ENUMERATE_SERVICE | win32service.SC_MANAGER_CONNECT
)
# This FAILS on non-admin:
sc = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
# → pywintypes.error: (5, 'OpenSCManager', 'Access is denied.')
```

## WMI (win32com) — Preferred for Service Enumeration

```python
import win32com.client
wmi = win32com.client.GetObject("winmgmts:")
for s in wmi.ExecQuery(
    "SELECT Name, DisplayName, State, ProcessId, StartMode, PathName "
    "FROM Win32_Service"
):
    start = {"Auto": 2, "Manual": 3, "Disabled": 4, "Boot": 0, "System": 1}.get(s.StartMode, -1)
    pid = int(s.ProcessId) if s.ProcessId else None
```

### `StopService()` return value
`StopService()` returns a tuple `(retcode,)` where `retcode` is a Win32 error code.
0 = success, 2 = access denied, others = various failures.

## Windows Process Memory

### Working set vs commit
- `rss` (psutil) = working set (physical memory resident)
- `vms` (psutil) = commit (page file / virtual address space)
- Normal Windows apps reserve 2-5x their working set as virtual address space.
- Only flag as pathological when ratio > 6x AND commit > 2GB.
- To flag a leak, use RSS *growth trend* (least-squares slope), not absolute ratio.

### Process creation time
`p.create_time()` returns a Unix epoch timestamp (float). Compare against `time.time()`
to compute process age. Skip leak detection for processes < 120s old (startup window).