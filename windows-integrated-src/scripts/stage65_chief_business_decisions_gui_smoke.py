"""Stage65 real Tk smoke in Linux Xvfb, socket/DNS forbidden."""
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
    with TemporaryDirectory(prefix='aiwack65-gui-') as tmp, \
         patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(Path(tmp) / 'owner.sqlite3'))
            app.account_name.set('owner65')
            app.account_password.set('stage65-long-password')
            app.password_confirm.set('stage65-long-password')
            app.auth_button.invoke(); root.update()
            assert '총괄 사업 판단 검토' in app.quick_navigation['values']
            assumptions = {'unit_price_krw': 10000, 'monthly_units': 10,
                           'unit_cost_krw': 3000, 'monthly_fixed_krw': 20000,
                           'monthly_marketing_krw': 10000, 'setup_cost_krw': 50000,
                           'refund_bps': 0, 'payment_fee_bps': 300, 'months': 6}
            ids = []
            for i in range(2):
                cid = app.store.generate_business_candidates(f'고객{i}', f'문제{i}', 1)['created_ids'][0]
                ids.append(app.store.evaluate_financial_scenario('candidate', cid, assumptions, '가정'))
            app.chief_business_eval_ids.set(','.join(map(str, ids)))
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app._chief_business_create(); root.update()
            assert app.store.chief_business_brief_history() == []
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._chief_business_create(); root.update()
            assert len(app.store.chief_business_brief_history()) == 1
            assert '실제 AI 판단' in app.chief_business_feedback.get()
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._chief_business_review('acknowledged'); root.update()
            assert app.store.chief_business_brief_history()[0]['review_status'] == 'acknowledged'
            assert app.store.list_businesses() == []
            app.sign_out(); root.update()
            app._chief_business_refresh(); root.update()
            assert '거부' in app.chief_business_feedback.get()
        finally:
            root.destroy()
    print('PASS Stage65 Tk: login, cancel, comparison, review-only, logout; no sockets/DNS')


if __name__ == '__main__':
    main()
