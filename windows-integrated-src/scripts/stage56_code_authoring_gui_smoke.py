"""Stage56 real GUI, approval cancellation, revision and signout denial. No model invoked."""
from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    with tempfile.TemporaryDirectory(prefix='aiwack-stage56-gui-') as tmp:
        db=Path(tmp)/'owner.sqlite3'
        root=tk.Tk()
        try:
            app=AIWACKWindow(root, LocalStore(db))
            app.account_name.set('stage56owner');app.account_password.set('stage56-long-owner-secret')
            app.password_confirm.set('stage56-long-owner-secret')
            app.auth_button.invoke();root.update()
            assert app.store.is_authenticated
            assert '로컬 AI 코드 초안' in app.quick_navigation['values']
            app.code_filename.set('result.py')
            app.code_editor.insert('1.0','def answer():\n    return 7\n')
            app.code_preview_button.invoke();root.update()
            assert '미리보기 완료' in app.code_feedback.get(), app.code_feedback.get()
            app.code_editor.insert('end','X')
            with patch('desktop.app.messagebox.askyesno',return_value=True):
                app.code_save_button.invoke();root.update()
            assert '다시 미리보기' in app.code_feedback.get(),app.code_feedback.get()
            app.code_editor.delete('1.0','end');app.code_editor.insert('1.0','def answer():\n    return 7\n')
            app.code_preview_button.invoke();root.update()
            with patch('desktop.app.messagebox.askyesno',return_value=False):
                app.code_save_button.invoke();root.update()
            assert not (Path(tmp)/'code_drafts'/'result.py').exists()
            app.code_preview_button.invoke();root.update()
            with patch('desktop.app.messagebox.askyesno',return_value=True):
                app.code_save_button.invoke();root.update()
            assert (Path(tmp)/'code_drafts'/'result.py').read_text()=='def answer():\n    return 7\n'
            app.code_editor.delete('1.0','end');app.code_editor.insert('1.0','def answer():\n    return 8\n')
            app.code_preview_button.invoke();root.update()
            with patch('desktop.app.messagebox.askyesno',return_value=True):
                app.code_save_button.invoke();root.update()
            assert app.store.list_code_drafts()[0]['version']==2
            app.sign_out();root.update()
            app._save_code_authoring()
            assert '거부' in app.code_feedback.get(),app.code_feedback.get()
        finally:
            root.destroy()
    print('PASS Stage56 GUI: preview, changed draft blocked, deny, approve, revision, sign-out deny')

if __name__=='__main__':main()
