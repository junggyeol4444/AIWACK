"""Native GUI integration test. Run under a real display or xvfb-run.

Creates and interacts with a real Tk window; no mocked GUI widgets or HTTP.
"""
from pathlib import Path
import tempfile
import tkinter as tk

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwack-gui-") as directory:
        db = Path(directory) / "gui.sqlite3"
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(db))
            root.update()
            assert root.winfo_exists(), "native Tk window did not open"
            assert "AIWACK" in root.title()
            assert len(app.roadmap_tree.get_children()) == 100
            app.tabs.select(1)
            app.note.set("PC 앱 창으로 저장 성공")
            app.save_button.invoke()  # actual native button callback
            root.update()
            assert "저장 완료" in app.feedback.get()
            assert app.store.read_note() == "PC 앱 창으로 저장 성공"
            app.note.set("다른 값")
            app.reload_note()
            root.update()
            assert app.note.get() == "PC 앱 창으로 저장 성공"
        finally:
            root.destroy()
        # Fully destroy & reopen the native GUI, verify persisted data.
        root2 = tk.Tk()
        try:
            app2 = AIWACKWindow(root2, LocalStore(db))
            root2.update()
            assert app2.note.get() == "PC 앱 창으로 저장 성공"
            assert root2.winfo_exists()
        finally:
            root2.destroy()
    print("PASS: native GUI window open, real button click, SQLite save, window shutdown, re-open, persisted value")


if __name__ == "__main__":
    main()
