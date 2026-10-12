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
            assert app.tabs.index("end") == 7, "admin center must be an actual notebook view"
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
            app.tabs.select(4)
            app.company_name.set("AIWACK 실사 회사")
            app.company_description.set("GUI에서 저장한 회사 설명")
            app.company_mission.set("윈도우 앱에서 실제 업무 관리")
            app.company_save_button.invoke()
            root.update()
            assert app.store.read_company()["name"] == "AIWACK 실사 회사"
            app.goal_title.set("창에서 직접 목표 추가")
            app.goal_detail.set("상태 변경/삭제도 확인")
            app.goal_add_button.invoke()
            root.update()
            assert len(app.goal_tree.get_children()) == 1
            goal_id = int(app.goal_tree.get_children()[0])
            app.goal_tree.selection_set(str(goal_id))
            root.update()
            app.goal_title.set("업데이트 된 목표")
            app.goal_status.set("active")
            app.goal_update_button.invoke()
            root.update()
            assert app.store.list_goals()[0]["title"] == "업데이트 된 목표"
            assert app.store.list_goals()[0]["status"] == "active"
            # Stage 12: actual native form buttons and SQLite CRUD.
            app.tabs.select(5)
            app.department_name.set("시장조사부")
            app.department_description.set("시장분석 및 기회 탐색")
            app.department_add_button.invoke()
            root.update()
            assert len(app.department_tree.get_children()) == 1
            department_id = str(app.store.list_departments()[0]["id"])
            app.department_tree.selection_set(department_id)
            root.update()
            app.department_name.set("시장조사·분석부")
            app.department_update_button.invoke()
            root.update()
            assert app.store.list_departments()[0]["name"] == "시장조사·분석부"
            app.admin_navigation["departments"].invoke()
            assert "1개" in app.admin_realtime.get()
            # Stage 13: exercise all three catalog classifications via real Tk buttons.
            app.tabs.select(6)
            root.update()
            for kind, label in (("rank", "팀장"), ("job", "시장조사"), ("role", "품질검수")):
                app.designation_kind.set(kind)
                app.designation_name.set(label)
                app.designation_description.set("직접 입력한 정의")
                app.designation_add_button.invoke()
                root.update()
            assert len(app.designation_tree.get_children()) == 3
            selected_designation = str(app.store.list_designations("role")[0]["id"])
            app.designation_tree.selection_set(selected_designation)
            root.update()
            app.designation_name.set("최종 품질검수")
            app.designation_update_button.invoke()
            root.update()
            assert app.store.list_designations("role")[0]["name"] == "최종 품질검수"
            app.admin_navigation["departments"].invoke()
            assert "3개" in app.admin_realtime.get()
            assert "AI 직원 정보 0건" in app.admin_realtime.get()
            assert app.store.list_employee_records() == []
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
            app2.tabs.select(4)
            assert app2.company_name.get() == "AIWACK 실사 회사"
            assert app2.store.list_goals()[0]["title"] == "업데이트 된 목표"
            # The delete UI requires explicit confirmation; stub only the dialog.
            from tkinter import messagebox
            original_confirm = messagebox.askyesno
            try:
                messagebox.askyesno = lambda *args, **kwargs: True
                app2.goal_tree.selection_set(app2.goal_tree.get_children()[0])
                app2.goal_delete_button.invoke()
                root2.update()
                assert app2.store.list_goals() == []
            finally:
                messagebox.askyesno = original_confirm
            app2.tabs.select(5)
            assert app2.store.list_departments()[0]["name"] == "시장조사·분석부"
            # No confirmation => no deletion.
            from tkinter import messagebox
            saved_confirm = messagebox.askyesno
            try:
                messagebox.askyesno = lambda *args, **kwargs: False
                app2.department_tree.selection_set(str(app2.store.list_departments()[0]["id"]))
                app2.department_delete_button.invoke()
                assert len(app2.store.list_departments()) == 1
                messagebox.askyesno = lambda *args, **kwargs: True
                app2.department_delete_button.invoke()
                root2.update()
                assert app2.store.list_departments() == []
            finally:
                messagebox.askyesno = saved_confirm
            app2.tabs.select(6)
            assert len(app2.store.list_designations()) == 3
            assert app2.store.list_designations("role")[0]["name"] == "최종 품질검수"
            from tkinter import messagebox
            saved_confirm = messagebox.askyesno
            try:
                messagebox.askyesno = lambda *args, **kwargs: False
                app2.designation_tree.selection_set(
                    str(app2.store.list_designations("role")[0]["id"]))
                app2.designation_delete_button.invoke()
                root2.update()
                assert len(app2.store.list_designations()) == 3
                messagebox.askyesno = lambda *args, **kwargs: True
                app2.designation_delete_button.invoke()
                root2.update()
                assert len(app2.store.list_designations()) == 2
            finally:
                messagebox.askyesno = saved_confirm
            app2.tabs.select(3)
            app2.admin_navigation["permissions"].invoke()
            assert app2.current_admin_section == "permissions"
            assert root2.winfo_exists()
        finally:
            root2.destroy()
    print("PASS: native Tk login, company/goal/department/designation CRUD, restart, persistence, access checks")


if __name__ == "__main__":
    main()
