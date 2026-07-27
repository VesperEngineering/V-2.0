# Windows Terminal fixed-size desktop launcher

Use this when a Windows TUI must start from a desktop shortcut at a defined physical pixel size.

## Key facts

- `wt.exe --maximized` overrides any startup-size intent.
- `wt.exe --size <columns>,<rows>` controls **terminal cells**, not physical pixels. It is suitable for a stable initial layout but cannot guarantee a pixel rectangle because font, DPI, padding, and titlebar vary.
- A `.lnk` pointing to a batch file often loses its intended branded icon. Keep `IconLocation` explicitly set on the shortcut.

## Reliable architecture

1. Desktop `.lnk` targets the venv's `pythonw.exe` so no temporary launcher console flashes.
2. Its sole argument is a small launcher script; set `WorkingDirectory` to the repository and `IconLocation` to the shipped `.ico`.
3. The launcher starts `wt.exe` with a unique `--title`, `-w new`, and a cell-size fallback such as `--size 256,33`.
4. Before launch, capture existing HWNDs whose title matches. Poll `EnumWindows` for a *new*, visible matching HWND.
5. Call `SetWindowPos` with the requested outer width/height (e.g. 2048×540). Center it using `GetSystemMetrics` if desired.
6. Time out and append a traceback to a repository-local launcher log so failures remain inspectable.

Use only ctypes/user32 APIs (`EnumWindows`, `IsWindowVisible`, `GetWindowTextW`, `GetWindowRect`, `SetWindowPos`) so the launcher does not require pywin32 in the app venv.

## Verification

Do not claim success merely because `WindowsTerminal.exe` exists. Verify all of:

1. Inspect the `.lnk`: target is `pythonw.exe`, arguments reference the launcher, working directory is repo root, and icon is the expected `.ico`.
2. Launch the actual desktop shortcut.
3. Enumerate visible windows by its unique title and assert `GetWindowRect` reports the exact requested outer size.
4. Run controller/layout tests, including a fake prompt-toolkit render. A layout can call a controller property that a prior restore/refactor removed, producing an immediate `AttributeError` only at first real render.

## PowerShell installer pitfall

A PowerShell script's `param(...)` block must be its first executable construct. Comments may precede it; variable assignments may not. Put installer version variables after `param`.
