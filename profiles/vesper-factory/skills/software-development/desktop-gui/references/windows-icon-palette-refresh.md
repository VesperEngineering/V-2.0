# Windows icon palette changes and shell-cache refresh

## Use when

A native Windows app or Desktop shortcut needs a deterministic icon recolor, or the rebuilt `.ico` is correct on disk but Windows still shows the previous icon.

## Source-of-truth workflow

1. Identify the complete contract before editing:
   - reviewable vector source (`.svg` or equivalent);
   - deterministic icon builder;
   - generated multi-size `.ico`;
   - focused branding test;
   - every shortcut/app that shares the asset.
2. Decide whether the recolor is shared branding or app-specific. A shared icon path updates every consumer; create a separate repository-owned asset when only one surface should change.
3. Update the palette test first and watch it fail. Assert exact semantic roles (field, mark, accent), reject retired colors when appropriate, and preserve geometry plus required ICO sizes.
4. Change builder constants and generated SVG descriptions/fills together. Do not hand-edit only the binary ICO.
5. Regenerate through the builder and run its deterministic `--check` mode.
6. Validate the raster, not only the SVG:
   - required Windows sizes are present (commonly 16, 24, 32, 48, 64, 128, 256);
   - a corner/background pixel matches the field;
   - the darkest/brightest semantic pixel matches the main mark;
   - the strongest accent-colored pixel remains distinguishable.

### Small-size antialiasing caveat

A narrow vector rail may map to less than one physical pixel at 16px. Its strongest pixel can therefore be a blend of the accent and background rather than the exact accent hex. Do not probe one assumed coordinate and require exact color at every size. Detect the strongest accent-like pixel (for an orange rail, strong red-over-green and green-over-blue separation), and separately inspect an enlarged nearest-neighbor 16px/32px frame.

## Refreshing the actual Windows surface

Rebuilding a same-path `.ico` does not prove the Desktop updated; Explorer caches icon content.

1. Re-save the `.lnk` through `WScript.Shell.CreateShortcut`, preserving target, arguments, working directory, description, and `IconLocation`.
2. Notify Shell without restarting Explorer:

```python
import ctypes

SHCNE_ASSOCCHANGED = 0x08000000
SHCNF_IDLIST = 0x0000
ctypes.windll.shell32.SHChangeNotify(
    SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None
)
```

3. Run `ie4uinit.exe -show` as a non-destructive cache refresh when available.
4. Avoid killing/restarting Explorer unless the user explicitly accepts the disruption. If same-path caching still persists, prefer a new stable repository-owned icon filename and update the shortcut rather than destructive cache deletion.
5. Close/relaunch any stale app instance: titlebar icons and newly added UI code are process-startup state. First inspect the live process command line so the relaunch targets the correct entrypoint.
6. Launch the actual Desktop `.lnk`, capture the titled HWND with Win32 `PrintWindow`, and verify:
   - the titlebar icon has the requested field/mark/accent roles;
   - newly requested UI text is present;
   - no controls clipped or shifted;
   - the process command line matches the shortcut contract.
7. If the user asked to see the result immediately, leave the verified final instance open; use a separate test instance for destructive close/PID checks when needed.

## Verification checklist

- Focused branding tests pass after an observed RED failure.
- Builder `--check`, lint, compilation, and `git diff --check` pass.
- All ICO sizes decode and satisfy semantic palette checks.
- Master and 16px/32px frames are visually inspected.
- Shortcut metadata is read back from COM.
- Actual shortcut-launched window is captured and checked.
- Only the intended tracked slice is staged; machine-local `.lnk` files remain uncommitted.
