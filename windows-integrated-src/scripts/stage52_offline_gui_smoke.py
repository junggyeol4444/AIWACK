"""Real Tkinter owner clicks for Stage52, with Python socket connections blocked."""
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def forbid(*a,**kw):
    raise AssertionError('unexpected network operation')


def login(app, new=False):
    app.account_name.set('stage52-owner')
    app.account_password.set('stage52-owner-password')
    if new:
        app.password_confirm.set('stage52-owner-password')
    app.auth_button.invoke()
    app.root.update()
    assert app.store.is_authenticated


def main():
    socket.socket.connect=forbid
    socket.socket.connect_ex=forbid
    socket.create_connection=forbid
    with tempfile.TemporaryDirectory(prefix='aiwack52-gui-') as directory:
        path=Path(directory)/'state.sqlite3'
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(path))
            login(app,new=True)
            assert '도구 사용 승인 검사' in app.quick_navigation['values']
            emp=app.store.add_employee_draft('emp_stage52','기술 직원')
            app.store.save_employee_access(emp,['company:read'],[])
            tool=app.store.register_ai_tool('local_reader_stage52','로컬 조회 후보','file','메타데이터만 등록','company:read')
            app.tool_use_key.set('request_stage52')
            app.tool_use_tool.set(str(tool))
            app.tool_use_employee.set(str(emp))
            app.tool_use_purpose.set('업무 자료 사전 조회 승인')
            app.tool_use_request_button.invoke();root.update()
            rows=app.store.list_ai_tool_use_requests()
            assert len(rows)==1 and rows[0]['status']=='pending',app.tool_use_feedback.get()
            app.tool_use_request_button.invoke();root.update()
            assert len(app.store.list_ai_tool_use_requests())==1,'duplicate request must be blocked'
            item=app.tool_use_tree.get_children()[0]
            app.tool_use_tree.selection_set(item)
            app.tool_use_check_button.invoke();root.update()
            assert '거부' in app.tool_use_feedback.get(),app.tool_use_feedback.get()
            app.tool_use_reason.set('관리자 승인 근거')
            app.tool_use_approve_button.invoke();root.update()
            assert app.store.read_ai_tool_use_request(rows[0]['id'])['status']=='approved',app.tool_use_feedback.get()
            item=app.tool_use_tree.get_children()[0]
            app.tool_use_tree.selection_set(item)
            app.tool_use_check_button.invoke();root.update()
            assert '조건 충족' in app.tool_use_feedback.get(),app.tool_use_feedback.get()
            app.store.save_employee_access(emp,[],[])
            app.tool_use_check_button.invoke();root.update()
            assert '거부' in app.tool_use_feedback.get(),app.tool_use_feedback.get()
            app.sign_out();root.update()
        finally:
            root.destroy()
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(path))
            login(app)
            r=app.store.read_ai_tool_use_request(1)
            assert r['status']=='approved'
            assert app.store.check_ai_tool_use(1)['allowed'] is False
            assert [a['event'] for a in app.store.ai_tool_use_audit(1)]==['requested','approved']
            print('PASS Stage52: real GUI request/duplicate/deny-preflight/approve/revoke/relogin; no network')
        finally:
            root.destroy()


if __name__=='__main__':main()
