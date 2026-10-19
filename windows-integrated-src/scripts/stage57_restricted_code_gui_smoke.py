"""Stage57 native GUI interaction. Does not execute unrestricted Python."""
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from unittest.mock import patch

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    with TemporaryDirectory(prefix='aiwack57-gui-') as tmp:
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(Path(tmp)/'owner.sqlite3'))
            app.account_name.set('owner57');app.account_password.set('local-owner-57-long-password')
            app.password_confirm.set('local-owner-57-long-password');app.auth_button.invoke();root.update()
            assert app.store.is_authenticated
            assert '제한형 코드 테스트' in app.quick_navigation['values']
            item=app.store.save_code_draft('answer.py','def answer():\n    return 7\n',0)
            app.restricted_id.set(str(item['id']))
            with patch('desktop.app.messagebox.askyesno',return_value=False):
                app.restricted_run_button.invoke();root.update()
            assert app.store.list_restricted_code_tests(item['id'])==[]
            with patch('desktop.app.messagebox.askyesno',return_value=True):
                app.restricted_run_button.invoke();root.update()
            assert '1/1' in app.restricted_feedback.get(),app.restricted_feedback.get()
            app.restricted_history_button.invoke();root.update()
            assert 'v1 1/1' in app.restricted_feedback.get()
            app.sign_out();root.update()
            app._run_restricted_code()
            assert '거부' in app.restricted_feedback.get(),app.restricted_feedback.get()
        finally:root.destroy()
    print('PASS Stage57 GUI: cancellation, explicit run, history, logout denial')

if __name__=='__main__':main()
