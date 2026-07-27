# Windows Service Categorization

A reusable technique for classifying Windows services by function, determining
whether they are safe to stop, and extracting their host executable and
dependency chains.

## Quick reference

```
memwatch services                     # all services grouped by category
memwatch services --detail Spooler    # full detail for one service
```

## Categories

| Category   | Meaning                          | Safe to stop? |
|------------|----------------------------------|---------------|
| `system`   | Windows core — breaks OS if gone | ❌ No         |
| `security` | AV / Defender / firewall         | ⚠️ With care  |
| `network`  | Networking stack                 | ⚠️ Lose net   |
| `hardware` | GPU / peripheral driver          | ✅ Lose device |
| `user`     | Third-party / user-installed     | ✅ Yes        |
| `disabled` | Start type = disabled            | Already off   |
| `unknown`  | Unclassified auto/demand service | Review first  |

## WMI query (preferred)

Use `win32com` WMI — it's more reliable across pywin32 builds than
`win32service.QueryServiceConfig`:

```python
import win32com.client
wmi = win32com.client.GetObject("winmgmts:")
query = ("SELECT Name, DisplayName, State, ProcessId, StartMode, PathName "
         "FROM Win32_Service")
for s in wmi.ExecQuery(query):
    pid = int(s.ProcessId) if (s.ProcessId and str(s.ProcessId).isdigit()) else None
    start = {"Auto": 2, "Manual": 3, "Disabled": 4, "Boot": 0, "System": 1}.get(s.StartMode, -1)
    path = (s.PathName or "").lower()
```

## Host executable extraction

```python
def _extract_host_exe(path: str) -> str:
    path = path.strip('"')
    base = path.rsplit("\\", 1)[-1] if "\\" in path else path
    base = base.split(" ")[0] if " " in base else base
    return base.lower()
```

## svchost -k group extraction

```python
import re
group = None
if "svchost.exe" in path_lower:
    m = re.search(r"-k\s+(\S+)", path_lower)
    if m:
        group = m.group(1)
```

## Dependency chains via Win32_DependentService

```python
dep_query = "SELECT Antecedent, Dependent FROM Win32_DependentService"
deps_raw: dict[str, list[str]] = {}
for r in wmi.ExecQuery(dep_query):
    ant = r.Antecedent.split('"')[1] if '"' in str(r.Antecedent) else ""
    dep = r.Dependent.split('"')[1] if '"' in str(r.Dependent) else ""
    if ant and dep:
        deps_raw.setdefault(ant, []).append(dep)
# deps_raw[name] = [services that depend on name]
```

## Categorization rules

```python
_SYSTEM_NAMES = {"RPCSS", "DcomLaunch", "LSASS", "Winmgmt", "EventLog",
                 "Schedule", "PlugPlay", "Power", "ProfSvc", ...}
_SECURITY_NAMES = {"MsMpEng", "WinDefend", "WdNisSvc",
                   "SecurityHealthService", ...}
_HARDWARE_PREFIXES = ("nv", "amd", "corsair", "intel", "realtek", "lghub", "logi_")
_NETWORK_NAMES = {"Dhcp", "NlaSvc", "Tcpip", "Dnscache", "WlanSvc", ...}
```

Heuristic for third-party services:
- `path` contains `"program files"`, `"users\\"`, or `"appdata"` → `user`
- Auto/manual start not in known system sets → `user`
- Start type `disabled` (4) → `disabled`

## Pitfalls

### StopService is already an int, not a callable

In this pywin32 build, `s.StopService` is a **property** that returns the
result code directly, not a method. **Do NOT call it with parentheses:**

```python
# WRONG — raises TypeError: 'int' object is not callable
ret = s.StopService()

# RIGHT — access the property, result is already the return code
ret = s.StopService
if ret == 0:
    print("Success")
```

Return codes: 0 = success, 2 = access denied (needs admin), other = various
WMI errors.

### Dependencies column may not be queryable

Some WMI schemas do not expose `Dependencies` as a direct column in
`Win32_Service`. Always use the separate `Win32_DependentService` association
query instead.

### win32service vs WMI

- `win32service.QueryServiceConfig` returns a **9-tuple**, not a dict; start
  type is at index 1.
- `SC_STATUS_PROCESS_INFO` may not exist in some pywin32 builds, making
  per-service PID unavailable via `win32service`.
- WMI (`win32com`) is preferred for per-service PID, correct start mode
  names, and PathName.