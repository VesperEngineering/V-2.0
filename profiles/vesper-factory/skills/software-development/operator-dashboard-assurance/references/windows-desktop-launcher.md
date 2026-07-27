# Windows Desktop Launcher and Readability Closure

Use this reference after dashboard data truth and action authority are verified.

## Visible desktop launcher

1. Resolve the interactive user's visible desktop with PowerShell:
   ```powershell
   [Environment]::GetFolderPath("Desktop")
   ```
   Do not infer it from `%USERPROFILE%\OneDrive\Desktop`.
2. Keep one authoritative launcher inside the repository. Login/startup wrappers and compatibility launchers should delegate to it rather than duplicate health-check logic.
3. For a browser/tray app, use a hidden `.vbs` wrapper when a console flash is undesirable, and create a `.lnk` with `WScript.Shell.CreateShortcut`:
   - target: `wscript.exe`
   - arguments: quoted path to the `.vbs`
   - working directory: authoritative application directory
   - icon: local `.ico`
   - description: plain operator-facing purpose
4. Make the launcher identity-aware: probe the loopback status endpoint for a stable contract and source-root identity before starting another process.
5. Launch the shortcut during verification. Assert:
   - shortcut exists at the Known Folder path;
   - target, arguments, working directory, and icon read back correctly;
   - loopback API reports the expected contract/source root;
   - listener PID before and after is unchanged when the app was already running.

A `.lnk` is the normal Windows desktop app entry point even when the underlying application is a browser/tray process. Do not claim a standalone `.exe` exists when it does not.

## Readability closure at desktop size

- Test at a representative constrained viewport such as 1280×625.
- Use minimum 12–13 px body/table text for dense operator views; headers can be 10–12 px when high contrast and uppercase.
- Prefer vertical scrolling over shrinking all content. Confirm `scrollHeight > clientHeight` where lower sections are intentionally below the fold.
- Overview tables should use fixed layouts and only essential columns. Long job names may wrap; status must remain visible.
- Remove empty factor columns. Render only payload-backed fields, and translate machine identifiers (`sec_insider_v2`) into readable display labels while retaining the raw value in a title/detail surface.
- Remove decorative window controls unless they invoke a real native host action.
- Use browser visual QA plus DOM inspection. A screenshot catches clipping; DOM checks prove repeated live values agree.

## Live-versus-snapshot consistency probe

After the live poll has completed, compare:

- top-strip P/L and day P/L;
- briefing P/L and day P/L;
- portfolio-panel P/L and day P/L;
- portfolio source label and observation time.

Keep a recent-live timestamp. Snapshot refreshes inside that freshness window must not overwrite live values. Recheck after at least one normal payload polling interval, because an initially correct live render can be silently replaced by the next snapshot render.
