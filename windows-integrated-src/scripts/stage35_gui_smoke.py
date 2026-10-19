"""Stage35 native Tk smoke: draft preview, owner approval, persistence and logout."""
from __future__ import annotations

from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='aiwack-stage35-gui-') as directory:
        path = Path(directory) / 'stage35.sqlite3'
        store = LocalStore(path)
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, store)
            app.account_name.set('owner35')
            app.account_password.set('stage35-gui-local-password')
            app.password_confirm.set('stage35-gui-local-password')
            app.auth_button.invoke()
            root.update()
            assert store.is_authenticated
            goal = store.add_goal('stage35 goal')
            store.update_goal(goal, 'stage35 goal', '', 'active')
            plan = store.add_work_plan(goal, 'six step plan', '',
                                       [f'Work step {n}' for n in range(1,7)], 'ready')
            app.tabs.select(23)
            root.update()
            choice = next(key for key, value in app.breakdown_plan_map.items() if value == plan)
            app.breakdown_plan_choice.set(choice)
            app.generate_task_breakdown()
            root.update()
            draft = store.list_task_breakdowns()[0]
            assert draft['status'] == 'draft' and draft['item_count'] == 6
            assert '실제 업무는 아직 생성되지' in app.breakdown_feedback.get()
            assert store.list_tasks() == []
            assert '선행: 1단계' in app.breakdown_details.get('1.0', 'end')
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app.apply_task_breakdown()
            assert store.list_tasks() == []
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app.apply_task_breakdown()
            assert len(store.list_tasks(plan)) == 6
            assert store.read_task_breakdown(draft['id'])['status'] == 'applied'
            assert store.list_task_runs() == []
            app.sign_out()
            root.update()
            assert not store.is_authenticated
            reopened = LocalStore(path)
            reopened.login('owner35', 'stage35-gui-local-password')
            assert len(reopened.list_tasks(plan)) == 6
            assert reopened.read_task_breakdown(draft['id'])['status'] == 'applied'
            print('PASS stage35 native GUI draft, preview, approval, restart and offline persistence')
        finally:
            root.destroy()


if __name__ == '__main__':
    main()
