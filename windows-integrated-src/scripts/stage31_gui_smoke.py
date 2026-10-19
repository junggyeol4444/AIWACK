"""Stage31 native Tk UI: login auto-check, manual check, logout timer safety."""
from __future__ import annotations

from pathlib import Path
import tempfile
import tkinter as tk

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='aiwack-stage31-gui-') as folder:
        db = LocalStore(Path(folder) / 'stage31.sqlite3')
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, db)
            app.account_name.set('owner31')
            app.account_password.set('stage31-safe-password')
            app.password_confirm.set('stage31-safe-password')
            app.auth_button.invoke()
            root.update()
            assert db.is_authenticated
            assert app.tabs.index('end') >= 22
            assert len(db.list_company_health_checks()) == 1  # automatic on login
            assert db.list_company_health_checks()[0]['severity'] == 'ok'
            assert app._health_timer_id is not None
            task = db.add_task('GUI31 local task')
            app.tabs.select(20)
            root.update()
            assert '담당자 없는 미완료 업무 1건' in app.health_summary.get()
            assert len(db.list_company_health_checks()) == 1  # tab read does not save
            # Simulate the scheduled callback without waiting five minutes.
            root.after_cancel(app._health_timer_id)
            app._health_timer_id = None
            app._health_timer_tick(app._session_generation)
            assert len(db.list_company_health_checks()) == 2  # changed aggregate auto-saved
            root.after_cancel(app._health_timer_id)
            app._health_timer_id = None
            app._health_timer_tick(app._session_generation)
            assert len(db.list_company_health_checks()) == 2  # identical auto check deduplicated
            app.manual_company_health_check()
            root.update()
            assert len(db.list_company_health_checks()) == 3
            assert db.read_task(task)['status'] == 'todo'
            assert '확인 필요' in app.health_summary.get()
            assert len(app.health_history.get_children()) == 3
            app.sign_out()
            root.update()
            assert not db.is_authenticated and app._health_timer_id is None
            reopened = LocalStore(db.path)
            reopened.login('owner31', 'stage31-safe-password')
            assert len(reopened.list_company_health_checks()) == 3
            assert reopened.read_task(task)['title'] == 'GUI31 local task'
            print('PASS stage31 GUI automatic login check, manual save, logout, persisted history')
        finally:
            root.destroy()


if __name__ == '__main__':
    main()
