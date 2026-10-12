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
            assert app.tabs.index("end") == 4, "admin center must be an actual notebook view"
            app.tabs.select(3)
            root.update()
            for key, title in (("overview", "회사 현황"), ("departments", "조직·직원"),
                               ("tasks", "업무·프로젝트"), ("business", "사업·상품"),
                               ("finance", "재무·매출"), ("permissions", "승인·권한"),
                               ("settings", "운영·설정")):
                app.admin_navigation[key].invoke()
                root.update()
                assert app.current_admin_section == key
                assert app.admin_title.get() == title
            assert "미구현" in app.admin_state.get()
            app.admin_navigation["permissions"].invoke()
            assert "owner" in app.admin_realtime.get()
            app.admin_navigation["overview"].invoke()
            assert "SQLite 정상" in app.admin_realtime.get()
            app.tabs.select(1)
            app.note.set("PC 앱 로그인 뒤 저장 성공")
            app.save_button.invoke()
            root.update()
            assert "저장 완료" in app.feedback.get()
            assert app.store.read_note() == "PC 앱 로그인 뒤 저장 성공"
            app.sign_out()
            root.update()
            assert not app.store.is_authenticated
            from desktop.storage import AuthenticationError
            try:
                app.show_admin_section("overview")
            except AuthenticationError:
                pass
            else:
                raise AssertionError("signed-out admin navigation must be refused")
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
            app2.tabs.select(3)
            app2.admin_navigation["permissions"].invoke()
            assert app2.current_admin_section == "permissions"
            assert root2.winfo_exists()
        finally:
            root2.destroy()
    print("PASS: Tk login, owner-only admin navigation, 7 sections, logout denial, restart and persisted note")


if __name__ == "__main__":
    main()
