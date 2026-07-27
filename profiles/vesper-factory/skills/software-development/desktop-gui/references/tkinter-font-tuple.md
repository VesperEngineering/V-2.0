# Tkinter Font Specification: Tuples vs Strings

## The Bug

Using a **string** font specifier with a space in the name causes:

```
_tkinter.TclError: expected integer but got "UI"
```

Example that breaks:
```python
master.option_add("*Font", "Segoe UI 10")     # ❌
```

## Why

Tkinter parses the string at the space boundaries. `"Segoe UI 10"` is split into `Segoe`, `UI`, `10`. Tk doesn't know `UI` is part of the font name — it expects an integer for the size field.

## The Fix

Pass fonts as **tuples**:

```python
master.option_add("*Font", ("Segoe UI", 10))  # ✅
```

## Style context

Same applies to `font=` parameter in `ttk.Style.configure()`, `tkinter.Widget.config()`, and canvas `.create_text()`:

```python
s.configure("TLabel", font=("Segoe UI", 10))   # ✅
self.log = tk.Text(..., font=("Consolas", 9))  # ✅
```

## Safe font tuple examples

| Family | Size | Code |
|--------|------|------|
| Segoe UI | 10 | `("Segoe UI", 10)` |
| Segoe UI bold | 10 | `("Segoe UI", 10, "bold")` |
| Consolas | 9 | `("Consolas", 9)` |
| Default | 10 | `("TkDefaultFont", 10)` |