# Windows Terminal full-screen redraw diagnostics

## Symptom

A Prompt Toolkit dashboard launched from a Windows desktop shortcut shows scattered numbers, partial values, or repeated lines scrolling downward instead of one stable dashboard frame.

## Root cause pattern

Windows Terminal hosts applications in a pseudoconsole. Forcing an ANSI output backend or invoking `mode con` from inside the application can conflict with the host's screen and cursor handling. The result is redraw output being appended to scrollback rather than repainting the alternate screen. The displayed values may look like PIDs or telemetry fragments, but they are usually pieces of successive dashboard frames.

## Safe division of responsibility

- Windows Terminal / launcher: window title, process invocation, working directory, and exact native HWND geometry.
- Prompt Toolkit: terminal output backend, full-screen application, cursor movement, and redraw lifecycle.
- Dashboard process: render state; it must not run `mode con` or force `PROMPT_TOOLKIT_OUTPUT=ansi`.

For exact pixel geometry, launch the uniquely titled window and resize its HWND from the launcher with `EnumWindows` and `SetWindowPos`. Do not attempt to enforce pixel dimensions from the dashboard process.

## Verification recipe

1. Compile the entrypoint and layout modules.
2. Run controller, layout, and shortcut tests with a repository-local pytest base directory if the default `%TEMP%\\pytest-of-<user>` root reports `WinError 5`.
3. Inspect the branded `.lnk` target, arguments, working directory, and icon.
4. Launch the actual `.lnk` with `os.startfile()` and wait for the exact visible title.
5. Assert the new HWND remains visible and its `GetWindowRect` dimensions match the requested rectangle.
6. Capture the window if visual confirmation is needed; close only the exact test window afterward.

A passing unit test or a running `python.exe` process alone does not prove that a full-screen terminal is repainting correctly.
