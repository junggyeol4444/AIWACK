"""Invoke real Tkinter buttons with a temporary persistent SQLite store."""
import tempfile
from pathlib import Path
import tkinter as tk

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    with tempfile.TemporaryDirectory(prefix='aiwack-stage42-gui-') as folder:
        root = tk.Tk()
        store = LocalStore(Path(folder) / 'company.sqlite3')
        try:
            app = AIWACKWindow(root, store)
            app.account_name.set('gui42_owner')
            app.account_password.set('safe-stage42-gui-password')
            app.password_confirm.set('safe-stage42-gui-password')
            app.auth_button.invoke()
            root.update()
            assert store.is_authenticated
            assert '부서별 협업 대화' in app.quick_navigation['values']
            department = store.add_department('GUI42부서')
            other = store.add_department('다른부서')
            employee = store.add_employee_draft('gui42_agent', 'GUI직원', department_id=department)
            app.tabs.select(app.quick_navigation['values'].index('부서별 협업 대화'))
            root.update()
            app.department_chat_department.set(str(department))
            app.department_chat_sender.set(str(employee))
            app.department_chat_body.insert('1.0', 'GUI 버튼을 통한 로컬 기록')
            app.department_chat_send_button.invoke()
            root.update()
            assert len(store.list_department_messages(department)) == 1, app.department_chat_feedback.get()
            assert len(app.department_chat_tree.get_children()) == 1
            app.department_chat_department.set(str(other))
            app.department_chat_refresh_button.invoke()
            root.update()
            assert len(app.department_chat_tree.get_children()) == 0
            app.department_chat_body.insert('1.0', '다른 부서 위조 시도')
            app.department_chat_send_button.invoke()
            assert len(store.list_department_messages(other)) == 0
            assert '활성 구성원이 아닙니다' in app.department_chat_feedback.get()
            app.sign_out()
            root.update()
            assert not store.is_authenticated
        finally:
            root.destroy()
    print('STAGE42 GUI SMOKE OK: Tk buttons, SQLite, department isolation and auth')


if __name__ == '__main__':
    main()
