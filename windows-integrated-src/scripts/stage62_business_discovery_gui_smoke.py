"""Stage62 real Tk GUI smoke, requires a display (e.g. xvfb-run)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from unittest.mock import patch

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    with TemporaryDirectory(prefix='aiwack62-gui-') as tmp:
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(Path(tmp) / 'owner.sqlite3'))
            app.account_name.set('owner62')
            app.account_password.set('stage62-long-password')
            app.password_confirm.set('stage62-long-password')
            app.auth_button.invoke(); root.update()
            assert '수익 사업 후보 가설' in app.quick_navigation['values']
            app.discovery_audience.set('1인 창업자')
            app.discovery_problem.set('반복 업무')
            app.discovery_limit.set('3')
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app.discovery_generate_button.invoke(); root.update()
            assert app.store.business_candidates() == []
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app.discovery_generate_button.invoke(); root.update()
            assert len(app.store.business_candidates()) == 3
            assert '시장 검증 없음' in app.discovery_feedback.get()
            app.discovery_tree.selection_set(app.discovery_tree.get_children()[0]); root.update()
            cid = int(app.discovery_candidate_id.get())
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app.discovery_state_button.invoke(); root.update()
            assert next(c for c in app.store.business_candidates() if c['id']==cid)['state']=='shortlisted'
            app.discovery_events_button.invoke(); root.update()
            assert 'state_changed' in app.discovery_feedback.get()
            app.sign_out(); root.update()
            app._discovery_refresh(); root.update()
            assert '거부' in app.discovery_feedback.get()
        finally:
            root.destroy()
    print('PASS Stage62 GUI: generation, cancel/approve, review, audit, logout denied')


if __name__ == '__main__':
    main()
