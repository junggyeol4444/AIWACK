"""Stage33 real Tk UI: auto proposal, approval, rejection, stale, logout, reopen."""
from __future__ import annotations

from pathlib import Path
import tempfile
import os
import time
import tkinter as tk
from unittest.mock import patch

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='aiwack-stage33-gui-') as folder:
        db = LocalStore(Path(folder) / 'stage33.sqlite3')
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, db)
            app.account_name.set('owner33')
            app.account_password.set('stage33-safe-password')
            app.password_confirm.set('stage33-safe-password')
            app.auth_button.invoke()
            root.update()
            assert db.is_authenticated
            assert app.tabs.index('end') >= 23  # later stages may append tabs
            assert app._health_timer_id is not None
            goal = db.add_goal('GUI confidential goal')
            db.update_goal(goal, 'GUI confidential goal', '', 'active')
            app.tabs.select(22)
            root.update()
            assert db.list_autonomous_task_proposals() == []  # read-only tab refresh
            app.scan_autonomous_task_proposals()
            root.update()
            assert len(app.autonomous_proposals_tree.get_children()) == 1
            proposal_id = int(app.autonomous_proposals_tree.get_children()[0])
            assert db.list_tasks() == []
            app.autonomous_proposals_tree.selection_set(str(proposal_id))
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app.approve_autonomous_task_proposal()
            assert db.list_tasks() == []
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app.approve_autonomous_task_proposal()
            root.update()
            assert len(db.list_tasks()) == 1
            task_id = db.list_tasks()[0]['id']
            assert db.read_task(task_id)['status'] == 'todo'
            assert db.list_task_runs() == []
            assert '등록 완료' in app.autonomous_proposals_feedback.get()
            assert db.list_autonomous_task_proposals()[0]['approved_task_id'] == task_id
            blocked = db.add_task('private blocked task')
            db.set_task_status(blocked, 'blocked')
            app.scan_autonomous_task_proposals()
            rows = db.list_autonomous_task_proposals()
            rejected_id = next(p['id'] for p in rows if p['source_kind'] == 'blocked_task')
            app.autonomous_proposals_tree.selection_set(str(rejected_id))
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app.reject_autonomous_task_proposal()
            assert db.list_autonomous_task_proposals()[0]['status'] == 'rejected'
            assert app._health_timer_id is not None
            root.after_cancel(app._health_timer_id)
            app._health_timer_id = None
            app._health_timer_tick(app._session_generation)
            assert len(db.list_autonomous_task_proposals()) == 2  # no duplicates
            if os.name != 'nt':
                chief = db.add_employee_draft('chief33', '로컬 총괄 AI')
                db.assign_reporting_line(chief, 'ceo')
                cli = Path(folder) / 'fake-local-cli'
                cli.write_text('#!/usr/bin/env python3\nprint("LOCAL")\n', encoding='utf-8')
                cli.chmod(0o700)
                model = Path(folder) / 'fake.gguf'
                model.write_bytes(b'GGUF\x03\x00\x00\x00')
                model_id = db.add_local_model(ModelConfig(
                    'local model', 'llama_cpp', str(cli), str(model), 16))
                db.set_employee_model(chief, model_id)
                new_goal = db.add_goal('AI context')
                db.update_goal(new_goal, 'AI context', '', 'active')
                app.scan_autonomous_task_proposals()
                with patch('desktop.autonomous_task_ai.invoke_chief_model',
                           return_value='{"title":"AI GUI idea","description":"Local only"}'):
                    app.toggle_auto_proposal_ai()
                    for _ in range(100):
                        root.update()
                        if any(p['origin'] == 'local_ai'
                               for p in db.list_autonomous_task_proposals()):
                            break
                        time.sleep(.02)
                assert any(p['origin'] == 'local_ai'
                           for p in db.list_autonomous_task_proposals())
                assert not any(t['title'] == 'AI GUI idea' for t in db.list_tasks())
                app.toggle_auto_proposal_ai()  # explicit stop
            app.sign_out()
            root.update()
            assert not db.is_authenticated and app._health_timer_id is None
            reopened = LocalStore(db.path)
            reopened.login('owner33', 'stage33-safe-password')
            assert len(reopened.list_autonomous_task_proposals()) == (3 if os.name != 'nt' else 2)
            assert reopened.read_task(task_id)['title'].startswith('활성 목표 #')
            assert len(reopened.list_task_runs()) == 0
            print('PASS stage33 GUI auto drafts, explicit approval/rejection, dedup, logout, persistence')
        finally:
            root.destroy()


if __name__ == '__main__':
    main()
