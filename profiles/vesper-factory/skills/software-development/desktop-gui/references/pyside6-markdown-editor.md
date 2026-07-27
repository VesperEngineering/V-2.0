# PySide6 Markdown reader/editor pattern

Use this pattern when a native desktop app must render Markdown, edit source, export PDF, support drag-and-drop, and provide normal document commands. Qt already supplies the hard parts; avoid simulating them in Tkinter.

## Recommended architecture

- `QMainWindow` with `QSplitter`
- `QPlainTextEdit` for Markdown source
- `QTextBrowser` for rendered preview
- Render with `preview.document().setMarkdown(text, QTextDocument.MarkdownDialectGitHub)`
- Set `document.setBaseUrl(QUrl.fromLocalFile(document_directory + "/"))` so relative images and links resolve
- Export rendered output with `QPrinter`, `PdfFormat`, and `preview.document().print_(printer)`
- `QSettings` for geometry, last directory, and recent files
- Accept drops on the main window; admit only known Markdown suffixes
- Track current path, dirty state, and an internal-update guard so opening a file does not mark it modified

## Document lifecycle

Every destructive transition—new, open, close, or application exit—must pass through one shared unsaved-changes guard. Saving should return `bool` so a cancelled Save As also cancels the pending destructive action.

Write Markdown as UTF-8. Read with `utf-8-sig` first to tolerate a BOM, then use a replacement fallback only when decoding fails.

## Views and commands

Provide split, preview-only, and editor-only modes. Apply zoom to both source and preview so switching modes does not produce inconsistent sizing. Keep the accumulated zoom delta and reverse it for reset.

Use `QAction` with standard `QKeySequence` values for Open, Save, Save As, Print/PDF, Find, clipboard actions, undo, and redo. Reuse the same actions in menus and toolbars.

## Verification

Use `pytest-qt` with `QT_QPA_PLATFORM=offscreen`. Cover at least:

1. Opening UTF-8 Markdown and seeing rendered text
2. Editing sets dirty state and Save writes exact text
3. Save As supplies a `.md` suffix when omitted
4. View-mode and zoom/reset behavior
5. PDF export creates a non-empty file beginning with `%PDF`

On Windows under a POSIX/MSYS shell, prefer a relative pytest `--basetemp` and set `TMP`/`TEMP` to a native `C:/...` path. Interpolating `$PWD` into a Windows program argument can be converted into an invalid `C:/c/...` path.

## Packaging and application identity

A small bootstrap `.bat` can run `uv sync` on first launch and then start `pythonw -m package.app`. For a distributable build, use PyInstaller `--windowed`; verify the produced executable separately rather than assuming source-level tests cover packaging.

Keep a PNG for runtime Qt display and a multi-resolution ICO for Windows executable branding:

```text
src/package/assets/icon.png
src/package/assets/icon.ico
```

Resolve the runtime image relative to `__file__`, then set it on both the application and main window:

```python
ICON_PATH = Path(__file__).resolve().parent / "assets" / "icon.png"
app.setWindowIcon(QIcon(str(ICON_PATH)))
window.setWindowIcon(QIcon(str(ICON_PATH)))
```

A Windows PyInstaller build needs both the executable icon and bundled runtime PNG:

```bat
pyinstaller --windowed --name "App Name" --paths src ^
  --icon src\package\assets\icon.ico ^
  --add-data "src\package\assets\icon.png;package\assets" ^
  src\package\app.py
```

Add a widget test asserting `window.windowIcon().isNull()` is false, then build and launch the packaged executable. Source tests alone do not validate PyInstaller resource paths.

If an inherited `PYTHONPATH` pollutes an isolated virtual environment during asset conversion or packaging, unset it for that command rather than adding unrelated packages to the project.