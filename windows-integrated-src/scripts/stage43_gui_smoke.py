"""Stage43 genuine Tk widgets, owner buttons, SQLite isolation with Xvfb."""
import tempfile
from pathlib import Path
import tkinter as tk

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    with tempfile.TemporaryDirectory(prefix='aiwack43-gui-') as tmp:
        root = tk.Tk()
        store = LocalStore(Path(tmp) / 'company.sqlite3')
        try:
            app = AIWACKWindow(root, store)
            app.account_name.set('gui43_owner')
            app.account_password.set('stage43-gui-safe-password')
            app.password_confirm.set('stage43-gui-safe-password')
            app.auth_button.invoke()
            root.update()
            assert store.is_authenticated
            assert '프로젝트 협업 대화' in app.quick_navigation['values']
            dept = store.add_department('개발팀')
            employee = store.add_employee_draft('employee43gui', 'GUI직원', department_id=dept)
            app.tabs.select(app.quick_navigation['values'].index('프로젝트 협업 대화'))
            root.update()
            app.project_chat_name.set('상품출시팀')
            app.project_chat_create_button.invoke()
            root.update()
            room = int(app.project_chat_project.get())
            assert len(store.list_project_rooms()) == 1
            app.project_chat_employee.set(str(employee))
            app.project_chat_add_button.invoke()
            assert len(store.list_project_participants(room)) == 1, app.project_chat_feedback.get()
            app.project_chat_body.insert('1.0', '실제 GUI에서 프로젝트 대화 등록')
            app.project_chat_send_button.invoke()
            root.update()
            assert len(store.list_project_messages(room)) == 1, app.project_chat_feedback.get()
            assert len(app.project_chat_tree.get_children()) == 1
            app.project_chat_name.set('별도프로젝트')
            app.project_chat_create_button.invoke()
            root.update()
            other = int(app.project_chat_project.get())
            assert other != room
            assert len(app.project_chat_tree.get_children()) == 0  # no old room data leakage
            app.project_chat_body.insert('1.0', '권한 없이 보내기')
            app.project_chat_send_button.invoke()
            assert '활성 참여자' in app.project_chat_feedback.get()
            assert store.list_project_messages(other) == []
            app.project_chat_project.set(str(room))
            app.project_chat_remove_button.invoke()
            assert store.list_project_participants(room) == []
            assert len(store.list_project_messages(room)) == 1
            app.project_chat_project.set('not-a-room')
            app.project_chat_refresh_button.invoke()
            assert not app.project_chat_tree.get_children()
            app.sign_out()
            root.update()
            assert not store.is_authenticated
        finally:
            root.destroy()
    print('STAGE43 GUI SMOKE OK: Tk interactions, project isolation, member controls, auth')


if __name__ == '__main__':
    main()
