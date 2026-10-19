"""Real Tkinter Stage47 owner-operated memory actions, with outbound sockets disabled."""
import socket
import sys
import tempfile
from pathlib import Path
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def forbidden(*args,**kwargs):
    raise AssertionError('External network forbidden')


def main():
    socket.socket.connect=forbidden
    socket.socket.connect_ex=forbidden
    with tempfile.TemporaryDirectory(prefix='aiwack47-') as temp:
        path=Path(temp)/'company.sqlite3'
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(path))
            app.account_name.set('stage47-owner')
            app.account_password.set('stage47-strong-local-password')
            app.password_confirm.set('stage47-strong-local-password')
            app.auth_button.invoke()
            root.update()
            assert app.store.is_authenticated
            assert '직원별 장기 기억' in app.quick_navigation['values']
            a=app.store.add_employee_draft('memory_gui_a','직원 A')
            b=app.store.add_employee_draft('memory_gui_b','직원 B')
            app.memory_employee.set(str(a))
            app.memory_kind.set('lesson')
            app.memory_title.set('고객 조사')
            app.memory_source.set('내부 실험 결과')
            app.memory_confidence.set('88')
            app.memory_content.insert('1.0','자료를 검증한다')
            app.memory_save_button.invoke();root.update()
            assert len(app.store.list_employee_memories(a))==1,app.memory_feedback.get()
            assert len(app.store.list_employee_memories(b))==0
            mid=app.store.list_employee_memories(a)[0]['id']
            app.memory_query.set('일치하지 않음')
            app.memory_refresh_button.invoke();root.update()
            assert not app.memory_tree.get_children()
            app.memory_query.set('고객')
            app.memory_refresh_button.invoke();root.update()
            selection=app.memory_tree.get_children()
            assert len(selection)==1
            app.memory_tree.selection_set(selection[0]);root.update()
            assert '자료를 검증한다' in app.memory_details.get('1.0','end')
            app.memory_archive_button.invoke();root.update()
            assert not app.memory_tree.get_children()
            assert app.store.read_employee_memory(a,mid)['archived_at']
            app.sign_out();root.update()
            assert not app.store.is_authenticated
        finally:root.destroy()
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(path))
            app.account_name.set('stage47-owner')
            app.account_password.set('stage47-strong-local-password')
            app.auth_button.invoke();root.update()
            assert app.store.read_employee_memory(a,mid)['content']=='자료를 검증한다'
            assert app.store.list_employee_memories(a)==[]
            print('PASS Stage47: offline GUI save/search/detail/archive, employee isolation, logout/relogin persistence')
        finally:root.destroy()


if __name__=='__main__':main()
