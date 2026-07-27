import tkinter as tk

import pytest


@pytest.fixture(scope="session")
def _tk_session_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def tk_root(_tk_session_root):
    root = _tk_session_root
    root.withdraw()
    yield root

    for callback_id in root.tk.call("after", "info"):
        try:
            root.after_cancel(callback_id)
        except tk.TclError:
            pass
    for child in root.winfo_children():
        child.destroy()
    root.update_idletasks()
