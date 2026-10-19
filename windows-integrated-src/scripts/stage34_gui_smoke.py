"""Stage34 real Tk owner workflow: live assessment, ranking, persistence, no run."""
from __future__ import annotations

from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='aiwack-stage34-gui-') as directory:
        path = Path(directory) / 'stage34.sqlite3'
        store = LocalStore(path)
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, store)
            app.account_name.set('owner34')
            app.account_password.set('stage34-safe-password')
            app.password_confirm.set('stage34-safe-password')
            app.auth_button.invoke()
            root.update()
            assert store.is_authenticated
            goal = store.add_goal('stage34 goal')
            store.update_goal(goal, 'stage34 goal', '', 'active')
            blocked = store.add_task('stage34 blocked')
            store.set_task_status(blocked, 'blocked')
            store.set_task_priority(blocked, 'urgent')
            app.tabs.select(22)
            root.update()
            app.scan_autonomous_task_proposals()
            root.update()
            proposals = store.list_autonomous_task_proposals()
            assert len(proposals) == 2
            ordered = [int(i) for i in app.autonomous_proposals_tree.get_children()]
            by_kind = {p['source_kind']: p['id'] for p in proposals}
            assert ordered == [by_kind['blocked_task'], by_kind['active_goal']]
            row = app.autonomous_proposals_tree.item(str(ordered[0]), 'values')
            assert row[4] == '95', row
            assert row[5] == '차단 해소 필요', row
            assert row[6] == '긴급', row
            app.autonomous_proposals_tree.selection_set(str(ordered[0]))
            app._show_task_proposal_analysis()
            assert '실행 가능 판정 아님' in app.autonomous_analysis_detail.get()
            assert '차단' in app.autonomous_analysis_detail.get()
            assert len(store.list_tasks()) == 1
            app.analyze_autonomous_task_proposals()
            assert '기존 분석 유지 2건' in app.autonomous_proposals_feedback.get()
            assert len(store.list_task_proposal_assessments()) == 2
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app.approve_autonomous_task_proposal()
            assert len(store.list_tasks()) == 1
            app.sign_out()
            root.update()
            assert not store.is_authenticated
            reopened = LocalStore(path)
            reopened.login('owner34', 'stage34-safe-password')
            assert len(reopened.list_task_proposal_assessments()) == 2
            assert reopened.list_task_runs() == []
            print('PASS stage34 native GUI ranking, evidence, explicit approval gate, SQLite persistence')
        finally:
            root.destroy()


if __name__ == '__main__':
    main()
