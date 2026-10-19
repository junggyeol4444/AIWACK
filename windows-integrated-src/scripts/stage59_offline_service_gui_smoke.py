"""Stage59 Tkinter smoke: local draft, cancel, review, no transmission, logout."""
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from unittest.mock import patch

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    with TemporaryDirectory(prefix='aiwack59-gui-') as tmp:
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(Path(tmp)/'owner.sqlite3'))
            app.account_name.set('owner59')
            app.account_password.set('stage59-owner-long-password')
            app.password_confirm.set('stage59-owner-long-password')
            app.auth_button.invoke();root.update()
            assert '외부 연동 초안 (오프라인)' in app.quick_navigation['values']
            app.service_kind.set('email')
            app.service_target.set('editor@example.com')
            app.service_title.set('Offline test')
            app.service_body.insert('1.0','Local only')
            with patch('desktop.app.messagebox.askyesno',return_value=False):
                app.service_prepare_button.invoke();root.update()
            assert app.store.service_draft_history()==[]
            with patch('desktop.app.messagebox.askyesno',return_value=True):
                app.service_prepare_button.invoke();root.update()
            assert app.service_draft_id.get()=='1',app.service_feedback.get()
            assert app.store.service_draft_detail(1)['state']=='prepared'
            with patch('desktop.app.messagebox.askyesno',return_value=False):
                app.service_review_button.invoke();root.update()
            assert app.store.service_draft_detail(1)['state']=='prepared'
            with patch('desktop.app.messagebox.askyesno',return_value=True):
                app.service_review_button.invoke();root.update()
            assert app.store.service_draft_detail(1)['state']=='reviewed_local_only'
            app._service_preview();root.update()
            assert 'Local only' in app.service_feedback.get()
            app._service_history();root.update()
            assert 'reviewed_local_only' in app.service_feedback.get()
            app.sign_out();root.update()
            app._service_history()
            assert '거부' in app.service_feedback.get()
        finally:
            root.destroy()
    print('PASS Stage59 GUI: cancel, save, review, preview, history, logout denied')

if __name__=='__main__':
    main()
