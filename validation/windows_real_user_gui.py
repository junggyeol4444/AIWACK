"""Windows real-input smoke test: physical mouse/keyboard via PyAutoGUI.
This is NOT a substitute for a personal Windows 11 device acceptance test.
Run only against the extracted AIWACK project from the validation branch.
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pyautogui
import tkinter as tk

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.12
ARTIFACTS = Path(os.environ.get("AIWACK_TEST_ARTIFACTS", "validation-artifacts")).resolve()
ARTIFACTS.mkdir(parents=True, exist_ok=True)
STEPS: list[str] = []

def record(label: str, root: tk.Tk) -> None:
    root.update()
    name = str(len(STEPS) + 1).zfill(2) + "-" + label
    try:
        pyautogui.screenshot().save(ARTIFACTS / (name + ".png"))
    except Exception as exc:
        (ARTIFACTS / (name + ".screenshot-error.txt")).write_text(repr(exc), encoding="utf-8")
    STEPS.append(label)

def click(root: tk.Tk, widget: tk.Widget) -> None:
    root.update()
    if not widget.winfo_viewable():
        raise AssertionError(f"widget not visible: {widget}")
    root.lift()
    root.focus_force()
    root.update()
    x = widget.winfo_rootx() + max(3, widget.winfo_width() // 2)
    y = widget.winfo_rooty() + max(3, widget.winfo_height() // 2)
    pyautogui.click(x, y)
    root.update()

def type_into(root: tk.Tk, widget: tk.Widget, value: str) -> None:
    click(root, widget)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.write(value, interval=0.015)
    root.update()

def find_button(parent: tk.Widget, text: str) -> tk.Button:
    for child in parent.winfo_children():
        if isinstance(child, tk.Button) and child.cget("text") == text:
            return child
        try:
            return find_button(child, text)
        except LookupError:
            pass
    raise LookupError(text)

def run_test() -> int:
    with tempfile.TemporaryDirectory(prefix="aiwack-win-user-") as directory:
        db = Path(directory) / "user.sqlite3"
        root = tk.Tk()
        try:
            root.geometry("1200x900+10+10")
            app = AIWACKWindow(root, LocalStore(db))
            record("first-launch", root)
            assert app.store.has_owner() is False
            type_into(root, app.username_entry, "windows_owner")
            type_into(root, app.password_entry, "Windows-test-2026-password")
            type_into(root, app.confirm_entry, "Windows-test-2026-password")
            click(root, app.auth_button)
            assert app.main_frame is not None, f"owner setup failed: {app.auth_feedback.get()}"
            record("owner-created", root)

            # Native Tk widget, physically clicked and typed rather than direct store mutation.
            root.update()
            if not app.note_entry.winfo_viewable():
                app.tabs.select(1)
                root.update()
            type_into(root, app.note_entry, "Saved through Windows mouse and keyboard")
            click(root, app.save_button)
            assert app.store.read_note() == "Saved through Windows mouse and keyboard"
            record("note-saved", root)

            click(root, find_button(root, "로그아웃"))
            assert app.main_frame is None
            record("signed-out", root)
            assert app.store.has_owner()

            type_into(root, app.username_entry, "windows_owner")
            type_into(root, app.password_entry, "Windows-test-2026-password")
            click(root, app.auth_button)
            assert app.main_frame is not None, f"re-login failed: {app.auth_feedback.get()}"
            assert app.note.get() == "Saved through Windows mouse and keyboard"
            record("relogged-and-persisted", root)

            # On an independent new LocalStore with no authenticated session, data must be denied.
            from desktop.storage import AuthenticationError
            no_session = LocalStore(db)
            try:
                no_session.read_note()
            except AuthenticationError:
                pass
            else:
                raise AssertionError("Unauthenticated read succeeded")
            return 0
        finally:
            (ARTIFACTS / "steps.json").write_text(json.dumps(STEPS, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                if root.winfo_exists():
                    root.destroy()
            except tk.TclError:
                pass

if __name__ == "__main__":
    try:
        code = run_test()
        print("WINDOWS REAL MOUSE/KEYBOARD GUI PASS", STEPS)
        raise SystemExit(code)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        (ARTIFACTS / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise SystemExit(1)
