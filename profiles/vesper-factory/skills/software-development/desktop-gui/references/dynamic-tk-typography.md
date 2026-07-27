# Dynamic Tk Typography Scaling

Use this recipe when a dense Tkinter monitor needs operator-adjustable text without restarting or breaking a fixed dashboard composition.

## Product contract

For this user's Vesper monitors:

- default to `110%` when the operator asks for "a little larger";
- expose `90%` through `130%` in `10%` steps;
- show a visible `Aa NNN%` control in the app bar;
- provide Larger, Smaller, and Reset commands plus `Ctrl++`, `Ctrl+-`, and `Ctrl+0`;
- persist the selected scale under `%LOCALAPPDATA%`, not beside the Desktop shortcut;
- resizing is presentation-only and grants no task, provider, broker, scheduler, approval, or execution authority.

## Managed-font architecture

Do not walk widgets and replace tuple fonts ad hoc. Use shared named fonts so existing widgets and newly rendered rows share the same live objects.

```python
import tkinter.font as tkfont

DEFAULT_TEXT_SCALE = 1.10
MIN_TEXT_SCALE = 0.90
MAX_TEXT_SCALE = 1.30
TEXT_SCALE_STEP = 0.10

self._text_scale = load_text_scale()
self._font_cache: dict[tuple[str, int, str], tkfont.Font] = {}

def _font(self, family: str, base_size: int, weight: str = "normal") -> tkfont.Font:
    key = (family, base_size, weight)
    font = self._font_cache.get(key)
    if font is None:
        font = tkfont.Font(
            root=self.root,
            family=family,
            size=max(8, round(base_size * self._text_scale)),
            weight=weight,
        )
        self._font_cache[key] = font
    return font
```

Route every widget and text-tag font through `_font(...)`. A static scan for literal `font=(` is a useful regression contract in a compact standalone monitor.

## Normalize and persist safely

- accept only finite values;
- round to supported steps;
- clamp to the allowed range;
- malformed or unreadable settings fall back to the default;
- write JSON to a same-directory temporary file, then atomically replace the settings file;
- a persistence failure must not prevent the live resize.

Keep settings separate from the monitor's read-only operational-data contract.

## Scale geometry with fonts

Font-only zoom is incomplete. Fixed-height bands that looked correct at 100% will clip at 130%.

Track and resize at least:

- app bar;
- rail header;
- worker rows already on screen;
- selected-task/focus header;
- tab bar;
- fixed popups and their wrap lengths.

Apply scaled heights both when widgets are created and when an existing window changes scale. Track recreated rows in a list so `_set_text_scale()` can resize the current instances immediately; ensure subsequent refreshes create rows at the active scale.

Do not blindly scale every padding value. First scale font objects and fixed clipping boundaries, then inspect the real layout.

## Responsive app-bar acceptance

At maximum scale, test with worst-case truthful data, not placeholders. Example:

```text
OAI 100% S · 100% W · OR $999.99
```

Assert the provider label and `Aa` control receive at least their requested width. Recover space from redundant chrome (long command captions, unused brand allocation, excess padding) before abbreviating operational data.

A long command caption and an ellipsis button are redundant. Compact decorative chrome first; keep provider, read-only, sync, and authority truth whole.

## TDD slices

Use vertical slices:

1. default/step/clamp normalization;
2. atomic settings round-trip;
3. malformed settings fallback;
4. an existing `tkfont.Font` changes size in place;
5. visible `Aa` menu and keyboard bindings;
6. worst-case app-bar labels do not clip at maximum scale;
7. existing structural bands and worker rows change pixel height live.

For Windows GUI tests, reuse one module-scoped `tk.Tk()` interpreter and give each test an isolated `tk.Toplevel`. Repeatedly creating and destroying independent interpreters in one pytest process is unnecessary; a shared interpreter also makes the test lifecycle deterministic. Deiconify only geometry tests before calling `winfo_width()`—a deliberately withdrawn window reports width `1`.

## Visual verification

1. Relaunch the actual Desktop shortcut so a stale process cannot hide source changes.
2. Capture the real shortcut-launched default window.
3. Exercise maximum scale through the app's own setter or menu, not a global hotkey.
4. Capture the app-local maximum-scale frame.
5. Inspect provider text, app-bar controls, brand subtitle, worker second lines, metrics, tabs, and popup wrapping.
6. Leave one authoritative shortcut-launched instance open at the persisted/default scale.

Never send global zoom hotkeys unless foreground ownership is proven. Prefer direct app methods for deterministic verification.
