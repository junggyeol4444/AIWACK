"""Stage61 real Tk GUI smoke: type, business, lifecycle, selection and logout."""
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from unittest.mock import patch

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    with TemporaryDirectory(prefix='aiwack61-gui-') as tmp:
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(Path(tmp) / 'owner.sqlite3'))
            app.account_name.set('owner61')
            app.account_password.set('stage61-owner-long-password')
            app.password_confirm.set('stage61-owner-long-password')
            app.auth_button.invoke(); root.update()
            assert '범용 사업 유형·사업 관리' in app.quick_navigation['values']
            app.business_type_key.set('my_business')
            app.business_type_title.set('새 사업 유형')
            app.business_type_add_button.invoke(); root.update()
            assert len(app.store.business_types()) == 15
            app.business_name.set('첫 계획')
            app.business_goal.set('시장 조사 이후 검토')
            app.business_budget.set('12000')
            app.business_create_button.invoke(); root.update()
            assert len(app.store.list_businesses()) == 1
            assert app.store.list_businesses()[0]['budget_krw'] == 12000
            business_id = app.store.list_businesses()[0]['id']
            app.business_tree.selection_set(app.business_tree.get_children()[0]); root.update()
            assert app.business_id.get() == str(business_id)
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app.business_state_button.invoke(); root.update()
            assert app.store.list_businesses()[0]['state'] == 'draft'
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app.business_state_button.invoke(); root.update()
            assert app.store.list_businesses()[0]['state'] == 'active'
            app.business_events_button.invoke(); root.update()
            assert 'state_changed' in app.business_feedback.get()
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app.business_type_disable_button.invoke(); root.update()
            assert app.store.business_types()[-1]['enabled'] == 1
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app.business_type_disable_button.invoke(); root.update()
            assert app.store.business_types()[-1]['enabled'] == 0
            assert len(app.store.list_businesses()) == 1
            app.sign_out(); root.update()
            app._business_refresh(); root.update()
            assert '거부' in app.business_feedback.get()
        finally:
            root.destroy()
    print('PASS Stage61 GUI: custom type, business, cancel/confirm, logout denied')


if __name__ == '__main__':
    main()
