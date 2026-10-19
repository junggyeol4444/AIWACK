"""Stage32 actual Tk smoke: local candidate detection, auto history, manual, logout."""
from __future__ import annotations

from pathlib import Path
import tempfile
import tkinter as tk

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='aiwack-stage32-gui-') as folder:
        db = LocalStore(Path(folder) / 'stage32.sqlite3')
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, db)
            app.account_name.set('owner32')
            app.account_password.set('stage32-safe-password')
            app.password_confirm.set('stage32-safe-password')
            app.auth_button.invoke()
            root.update()
            assert db.is_authenticated
            assert app.tabs.index('end') >= 22
            assert len(db.list_company_detection_checks()) == 1
            assert app._health_timer_id is not None
            goal = db.add_goal('GUI private goal')
            db.update_goal(goal, 'GUI private goal', '', 'active')
            app.tabs.select(21)
            root.update()
            assert '내부 기회 후보 1종' in app.detection_summary.get()
            assert len(db.list_company_detection_checks()) == 1  # live read, no write
            rows = app.detection_signals.get_children()
            assert len(rows) == 1
            assert app.detection_signals.item(rows[0], 'values')[4] == str(goal)
            root.after_cancel(app._health_timer_id)
            app._health_timer_id = None
            app._health_timer_tick(app._session_generation)
            assert len(db.list_company_detection_checks()) == 2
            root.after_cancel(app._health_timer_id)
            app._health_timer_id = None
            app._health_timer_tick(app._session_generation)
            assert len(db.list_company_detection_checks()) == 2  # unchanged
            app.manual_company_detection()
            root.update()
            assert len(db.list_company_detection_checks()) == 3
            assert '저장 완료' in app.detection_feedback.get()
            assert len(app.detection_history.get_children()) == 3
            assert len(db.list_tasks()) == 0
            app.sign_out()
            root.update()
            assert not db.is_authenticated and app._health_timer_id is None
            reopened = LocalStore(db.path)
            reopened.login('owner32', 'stage32-safe-password')
            assert len(reopened.list_company_detection_checks()) == 3
            assert reopened.list_goals()[0]['title'] == 'GUI private goal'
            print('PASS stage32 GUI login auto-detection, candidate, dedup, manual, logout, persistence')
        finally:
            root.destroy()


if __name__ == '__main__':
    main()
