---
name: wsl-desktop-integration
description: "Create Windows desktop shortcuts and launchers from POSIX shells (git-bash, MSYS, WSL) — bridging WSL scripts, Python virtualenv apps, and the Windows desktop."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [WSL, Windows, Shortcuts, Desktop, Vesper, Codex]
    related_skills: [vesper-cron-operations, codex]
---

# Windows Desktop Shortcuts from POSIX Shells

Create Windows shortcuts (`.lnk`) and launchers from git-bash, MSYS, or WSL terminals. Covers both WSL scripts and native Windows Python apps (virtualenv, conda, etc.).

## When to Use What

| Target | Method | Why |
|---|---|---|
| WSL shell script | PowerShell `.ps1` → `wsl.exe` | Native WSL bridge |
| Windows `.exe` (Python venv, etc.) | VBScript `.vbs` | Simpler quoting than PowerShell from git-bash |
| Custom icon | Python + PIL | Cross-platform generation, multi-resolution |

## Core Concepts

### Filesystem Mapping

| Context | `~/Desktop` resolves to | Notes |
|---|---|---|
| **Windows (git-bash, PowerShell, cmd)** | `C:\Users\<user>\Desktop` | The actual Windows desktop |
| **WSL (bash inside WSL)** | `/home/<user>/Desktop` | A directory inside the WSL VM — **not** the Windows desktop |
| **WSL accessing Windows** | `/mnt/c/Users/<user>/Desktop/` | The actual Windows desktop, reachable via the `/mnt/c/` mount |

**Rule:** `~/Desktop` inside WSL is NOT the Windows desktop. If the user wants a file on their Windows desktop from a WSL terminal, they must copy/use the `/mnt/c/Users/<user>/Desktop/` path.

### `.desktop` Files Don't Work on Windows

Linux `.desktop` launcher files (freedesktop.org standard) are **not natively executable on Windows**. Even if copied to the Windows desktop:
- Windows doesn't understand the `[Desktop Entry]` format
- The `Exec=` path (e.g. `/home/brennan/.../script.sh`) is a WSL-internal path Windows can't resolve
- Double-clicking a `.desktop` file on Windows either does nothing or opens it in a text editor

### Windows `.lnk` Shortcuts

Windows shortcut files (`.lnk`) are the correct cross-platform launcher. They can target `wsl.exe` (for WSL scripts) or any Windows executable (for Python venv apps, etc.).

## Creating a Non-WSL Shortcut (Python Virtualenv App)

When the target is a Windows executable — e.g. a Python app in a local virtualenv — use **VBScript** instead of PowerShell. VBScript has simpler quoting rules from git-bash/MSYS and avoids `powershell.exe -ExecutionPolicy Bypass` overhead.

### Method: VBScript → `cscript //NoLogo`

Write a temporary `.vbs` file, run it with `cscript`, then delete it:

```bash
cat << 'VBSEOF' > /c/Users/<user>/Desktop/make-shortcut.vbs
Set WshShell = CreateObject("WScript.Shell")
Set oLink = WshShell.CreateShortcut("C:\Users\<user>\Desktop\My App.lnk")
oLink.TargetPath = "C:\Users\<user>\Desktop\v20\.venv\Scripts\python.exe"
oLink.Arguments = "-m vesper.dashboard.app"
oLink.WorkingDirectory = "C:\Users\<user>\Desktop\v20"
oLink.Description = "My App Description"
oLink.IconLocation = "C:\Users\<user>\Desktop\v20\assets\dashboard.ico,0"
oLink.Save
VBSEOF
cscript //NoLogo "C:\Users\<user>\Desktop\make-shortcut.vbs"
rm -f "C:\Users\<user>\Desktop\make-shortcut.vbs"
```

### Key `.lnk` Parameters (Non-WSL)

| Field | Example Value | Notes |
|---|---|---|
| `TargetPath` | `C:\Users\<user>\Desktop\v20\.venv\Scripts\python.exe` | Absolute path to the Windows executable |
| `Arguments` | `-m vesper.dashboard.app` | Module or script to run |
| `WorkingDirectory` | `C:\Users\<user>\Desktop\v20` | Working directory for relative paths |
| `IconLocation` | `C:\...\assets\dashboard.ico,0` | `,0` selects the first icon in the file |
| `Description` | Human-readable | Tooltip text |

## Generating Multi-Resolution Icons from Python

PIL's `Image.save(..., format="ICO", append_images=...)` **does not produce valid multi-image ICOs** — it only writes the first image. To create a proper Windows icon with multiple resolutions (16, 32, 48, 256 px), manually construct the ICO file with PNG payloads.

See `references/ico-generation.md` for the exact working script.

### Quick Verification

After generating, verify the ICO contains all sizes:

```python
import struct
with open(r"C:\Users\<user>\Desktop\v20\assets\dashboard.ico", "rb") as f:
    data = f.read()
count = struct.unpack("<HHH", data[:6])[2]
sizes = []
offset = 6
for i in range(count):
    w, h = data[offset], data[offset + 1]
    sizes.append(w if w else 256)
    offset += 16
print(f"Sizes: {sizes}")  # Should be [16, 32, 48, 256]
```

Verify the `.lnk` references the icon:

```python
with open(r"C:\Users\<user>\Desktop\My App.lnk", "rb") as f:
    assert b"dashboard.ico" in f.read()
```

## Creating a WSL Shortcut on the Windows Desktop

### Method: PowerShell (produces a proper `.lnk`)

Write a temporary PowerShell script on the desktop, then run it:

```powershell
# Create the .ps1 file on the desktop
$script = @"
`$WshShell = New-Object -ComObject WScript.Shell
`$Shortcut = `$WshShell.CreateShortcut("`$env:USERPROFILE\Desktop\My Tool Name.lnk")
`$Shortcut.TargetPath = "wsl.exe"
`$Shortcut.Arguments = "/home/user/project/scripts/tool.sh"
`$Shortcut.WorkingDirectory = "/home/user/project"
`$Shortcut.WindowStyle = 7
`$Shortcut.Description = "Description of what this launches"
`$Shortcut.Save()
Write-Output "Shortcut created"
"@
$script | Out-File -FilePath "$env:USERPROFILE\Desktop\make-shortcut.ps1" -Encoding ASCII
```

Then run it:
```bash
powershell.exe -ExecutionPolicy Bypass -File "C:\Users\<user>\Desktop\make-shortcut.ps1"
```

Then **clean up the temp script**:
```bash
rm -f "C:\Users\<user>\Desktop\make-shortcut.ps1"
```

### Key `.lnk` Parameters (WSL)

| Field | Value | Notes |
|---|---|---|
| `TargetPath` | `wsl.exe` | Windows executable that bridges to WSL |
| `Arguments` | `/home/user/project/scripts/tool.sh` | Absolute path to the script **inside WSL** |
| `WorkingDirectory` | `/home/user/project` | WSL working directory when script runs |
| `WindowStyle` | `7` | Minimized (7) — no console window flashing |
| `Description` | Human-readable | Tooltip text |

### Alternative: `.bat` / `.cmd` File

Simpler but shows a console window briefly:

```batch
@echo off
wsl /home/user/project/scripts/tool.sh
```

Save as `My Tool.bat` on the desktop.

## Windows Startup Folder Launchers

Use a Startup-folder `.bat`/`.cmd` only when the user wants an app launched at interactive logon. The per-user folder is:

```text
C:\Users\<user>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup
```

For a native Windows Python GUI, use the app's project-local interpreter, explicitly set the working directory, and quote all paths:

```batch
@echo off
rem Project dashboard — auto-start at logon
cd /d "C:\Users\<user>\Desktop\project"
start "Project Dashboard" /min "C:\Users\<user>\Desktop\project\.venv\Scripts\pythonw.exe" "scripts\dashboard.py"
```

Before changing an existing Startup entry:

1. Inspect the actual file in the Startup folder. A pasted script or legacy disabled file may not be the active entry.
2. Confirm the project root, entrypoint, and interpreter exist. Prefer the target project's `.venv\Scripts\pythonw.exe` over an unrelated tool environment.
3. Preserve the stated workspace authority: do not repoint a launcher to frozen or legacy material merely because an old script names it.
4. Avoid launching an extra GUI solely to test the change. Verify paths and, for Python entrypoints, use a no-side-effect syntax check when possible.

To disable a Startup launcher reversibly, rename its executable suffix rather than deleting it:

```text
Project Dashboard.bat  ->  Project Dashboard.bat.disabled
```

Confirm the executable `.bat`/`.cmd` no longer exists and the `.disabled` copy does exist. This removes logon execution while retaining an exact recovery artifact.

## Desktop observers backed by WSL state

A direct `wsl.exe` shortcut is appropriate for a non-interactive WSL command, but it is not by itself a reliable desktop-TUI contract. A curses/ANSI program needs an attached pseudoconsole and a paced input loop; otherwise it can flash closed or spin at full CPU when `nodelay()` returns immediately.

When the user needs a dependable Desktop monitoring/control surface while the model environment remains in WSL:

1. Prefer a small **native Windows Tkinter** console launched by `pythonw.exe` over a direct WSL curses shortcut.
2. Keep the source of truth in WSL. Have the native UI invoke a fixed, allowlisted WSL exporter command asynchronously, parse a bounded JSON snapshot, and retain the last successful display on refresh errors.
3. Route an explicit user action such as “Run training” through one fixed WSL wrapper; never interpolate UI text into shell commands.
4. Use a background thread/queue for WSL subprocesses. Tk callbacks must only update widgets on the Tk thread; use `after()` for periodic refresh and cancel scheduled callbacks on close.
5. The shortcut installer must target the exact `pythonw.exe`, quote the entrypoint, and set the project working directory. Compute the project root from the installer location carefully—`scripts/windows` is two parents below the project root.
6. Verify the real Desktop path: inspect target/arguments/working directory, launch the `.lnk`, assert a responsive titled native window appears, then close only the verification process. A source-level smoke test is insufficient.

For a terminal UI that remains appropriate, add a small sleep such as `curses.napms(100)` to every nonblocking input iteration and test it in a real terminal host, not only through redirected standard streams.

## Pitfalls

- **Inline PowerShell from git-bash/MSYS**** — complex quoting rules cause parser errors. Always write the PowerShell script to a `.ps1` file first, then run it.
- **Use ASCII shortcut filenames through a Git-Bash → PowerShell path.** Terminal code-page conversion can corrupt typographic punctuation such as an em dash, creating a shortcut that later inspection or cleanup cannot address by its expected name. Prefer names like `Project - Console.lnk`, then inspect the exact created path immediately after saving.
- **VBScript is simpler than PowerShell for non-WSL targets** — no `-ExecutionPolicy Bypass`, no `$` escaping, just plain `Set oLink = ...`.
- **Clean up temp files** — user doesn't want leftover `.ps1`, `.vbs`, or `.bat` files on their desktop after the shortcut is created.
- **WSL path must be absolute** — the script path in Arguments must start from WSL's root (`/home/...`), not a relative or Windows-style path.
- **`wsl.exe` must be on PATH** — it's installed by default with WSL at `C:\Windows\System32\wsl.exe`.
- **PIL `append_images` doesn't create multi-image ICOs** — see `references/ico-generation.md` for the working manual construction.
- **Windows caches icon images** — after changing a `.ico` file, the desktop may still show the old icon until you refresh (F5) or log out/in.
