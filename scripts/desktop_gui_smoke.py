"""Real Tk widget buttons and persisted owner login in two real GUI lifetimes."""
from pathlib import Path
import tempfile
import tkinter as tk

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwack-gui-") as directory:
        path = Path(directory) / "gui.sqlite3"
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(path))
            root.update()
            assert root.winfo_exists()
            assert "AIWACK" in root.title()
            assert not hasattr(app, "tabs"), "Dashboard should not appear before first setup"
            app.account_name.set("owner_test")
            app.account_password.set("my-strong-password-2026")
            app.password_confirm.set("not-matching")
            app.auth_button.invoke()
            root.update()
            assert not app.store.has_owner()
            app.password_confirm.set("my-strong-password-2026")
            app.auth_button.invoke()
            root.update()
            assert app.store.is_authenticated
            assert len(app.roadmap_tree.get_children()) == 100
            app.tabs.select(1)
            app.note.set("PC 앱 로그인 뒤 저장 성공")
            app.save_button.invoke()
            root.update()
            assert "저장 완료" in app.feedback.get()
            assert app.store.read_note() == "PC 앱 로그인 뒤 저장 성공"
            app.sign_out()
            root.update()
            assert not app.store.is_authenticated
            app.account_name.set("owner_test")
            app.account_password.set("wrong_password")
            app.auth_button.invoke()
            root.update()
            assert not app.store.is_authenticated
            app.account_password.set("my-strong-password-2026")
            app.auth_button.invoke()
            root.update()
            assert app.store.is_authenticated
            assert app.note.get() == "PC 앱 로그인 뒤 저장 성공"
        finally:
            root.destroy()
        root2 = tk.Tk()
        try:
            app2 = AIWACKWindow(root2, LocalStore(path))
            root2.update()
            assert not app2.store.is_authenticated
            assert not hasattr(app2, "tabs")
            app2.account_name.set("owner_test")
            app2.account_password.set("my-strong-password-2026")
            app2.auth_button.invoke()
            root2.update()
            assert app2.note.get() == "PC 앱 로그인 뒤 저장 성공"
            assert root2.winfo_exists()
        finally:
            root2.destroy()
    print("PASS: actual Tk setup/login/buttons/logout/reopen/persistent note and access gating")


if __name__ == "__main__":
    main()
