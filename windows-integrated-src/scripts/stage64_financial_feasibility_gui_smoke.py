"""Stage64 real Tk smoke (Linux Xvfb; Windows remains unverified)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import socket
import tkinter as tk
from unittest.mock import patch

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    def forbidden(*args, **kwargs):
        raise AssertionError('network forbidden')
    with TemporaryDirectory(prefix='aiwack64-gui-') as tmp, \
         patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(Path(tmp) / 'owner.sqlite3'))
            app.account_name.set('owner64')
            app.account_password.set('stage64-long-password')
            app.password_confirm.set('stage64-long-password')
            app.auth_button.invoke(); root.update()
            assert '비용·수익 가정 평가' in app.quick_navigation['values']
            candidate = app.store.generate_business_candidates('고객', '문제', 1)['created_ids'][0]
            app.finance_subject_id.set(str(candidate))
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app.finance_evaluate_button.invoke(); root.update()
            assert app.store.financial_scenario_history('candidate', candidate) == []
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app.finance_evaluate_button.invoke(); root.update()
            assert len(app.store.financial_scenario_history('candidate', candidate)) == 1
            assert '실제 매출' in app.finance_feedback.get()
            app.finance_tree.selection_set(app.finance_tree.get_children()[0]); root.update()
            assert int(app.finance_eval_id.get()) > 0
            app.finance_report_button.invoke(); root.update()
            assert '무결성 확인' in app.finance_feedback.get()
            app.sign_out(); root.update()
            app._finance_refresh(); root.update()
            assert '거부' in app.finance_feedback.get()
        finally:
            root.destroy()
    print('PASS Stage64 Tk: owner, cancel, save, scenario, audit, logout denial; no sockets/DNS')


if __name__ == '__main__':
    main()
