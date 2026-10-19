"""Stage66 real Tk smoke in Linux Xvfb; no socket or DNS access."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import socket
import tkinter as tk

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    def forbidden(*args, **kwargs):
        raise AssertionError('network forbidden')
    with TemporaryDirectory(prefix='aiwack66-gui-') as tmp, \
         patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(Path(tmp) / 'owner.sqlite3'))
            app.account_name.set('owner66')
            app.account_password.set('stage66-long-password')
            app.password_confirm.set('stage66-long-password')
            app.auth_button.invoke(); root.update()
            assert '다중 사업·프로젝트 관리' in app.quick_navigation['values']
            a = app.store.create_business(1, '사업 A', '목표 A')
            b = app.store.create_business(2, '사업 B', '목표 B')
            app.business_project_business_id.set(str(a))
            app.business_project_title.set('첫 프로젝트')
            app.business_project_objective.set('로컬 계획')
            app.business_project_budget.set('12345')
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app._business_project_create(); root.update()
            assert app.store.business_projects() == []
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._business_project_create(); root.update()
            p = app.store.business_projects()[0]['id']
            assert app.store.business_project(p)['planned_budget_krw'] == 12345
            t = app.store.add_task('기존 업무')
            app.business_project_task_id.set(str(t))
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._business_project_task(True); root.update()
            assert app.store.business_project(p)['task_ids'] == [t]
            app.business_project_state.set('active')
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._business_project_state_change(); root.update()
            assert app.store.business_project(p)['state'] == 'active'
            assert app.store.read_task(t)['status'] == 'todo'
            app.business_project_business_id.set(str(b))
            app.business_project_title.set('두 번째 사업 프로젝트')
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._business_project_create(); root.update()
            assert len(app.store.business_projects()) == 2
            app.sign_out(); root.update()
            app._business_project_refresh(); root.update()
            assert '거부' in app.business_project_feedback.get()
        finally:
            root.destroy()
    print('PASS Stage66 Tk: owner login, cancel, two businesses, task link, state, logout; sockets/DNS blocked')


if __name__ == '__main__':
    main()
