"""Stage51 native Tkinter button and SQLite persistence test without network."""
import socket
import sys
import tempfile
from pathlib import Path
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def forbid(*args, **kwargs):
    raise AssertionError('network operation forbidden')


def main():
    socket.socket.connect = forbid
    socket.socket.connect_ex = forbid
    socket.create_connection = forbid
    with tempfile.TemporaryDirectory(prefix='aiwack51-') as directory:
        db_path = Path(directory) / 'company.sqlite3'
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(db_path))
            app.account_name.set('stage51-owner')
            app.account_password.set('stage51-password-secure')
            app.password_confirm.set('stage51-password-secure')
            app.auth_button.invoke(); root.update()
            assert app.store.is_authenticated
            assert 'AI 작업 도구 등록' in app.quick_navigation['values']
            app.registry_key.set('file_report_helper')
            app.registry_name.set('파일 분석 도구 후보')
            app.registry_category.set('file')
            app.registry_description.set('실행이 연결되지 않은 로컬 후보 정보')
            app.registry_capability.set('company:read')
            app.registry_create_button.invoke(); root.update()
            tools = app.store.list_registered_ai_tools()
            assert len(tools)==1, app.registry_feedback.get()
            assert tools[0]['required_capability']=='company:read'
            app.registry_create_button.invoke(); root.update()
            assert len(app.store.list_registered_ai_tools())==1, 'duplicate key must be rejected'
            row=app.registry_tree.get_children()[0]
            app.registry_tree.selection_set(row)
            app.registry_retire_reason.set('관리자 계획 변경')
            app.registry_retire_button.invoke(); root.update()
            assert app.store.read_registered_ai_tool(tools[0]['id'])['state']=='retired', app.registry_feedback.get()
            app.sign_out();root.update()
            assert not app.store.is_authenticated
        finally:
            root.destroy()
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(db_path))
            app.account_name.set('stage51-owner')
            app.account_password.set('stage51-password-secure')
            app.auth_button.invoke();root.update()
            assert len(app.store.list_registered_ai_tools(include_retired=True))==1
            assert len(app.store.registered_ai_tool_audit(1))==2
            assert app.store.list_registered_ai_tools()==[]
            print('PASS Stage51: native GUI register/duplicate/retire/relogin, no network')
        finally:
            root.destroy()


if __name__=='__main__': main()
