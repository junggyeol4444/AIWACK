"""Stage58 actual Tkinter adapter tab: cancellation, approval, audit, logout."""
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from unittest.mock import patch
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    with TemporaryDirectory(prefix='aiwack58-gui-') as tmp:
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(Path(tmp)/'owner.sqlite3'))
            app.account_name.set('owner58');app.account_password.set('stage58-owner-long-password')
            app.password_confirm.set('stage58-owner-long-password');app.auth_button.invoke();root.update()
            assert '이미지·영상·문서 어댑터' in app.quick_navigation['values']
            p=Path(tmp)/'notes.txt';p.write_text('local content',encoding='utf-8')
            app.media_adapter.set('document_text')
            with patch('desktop.app.filedialog.askopenfilename',return_value=str(p)):
                app._media_choose_file()
            assert app.media_file.get()==str(p)
            with patch('desktop.app.messagebox.askyesno',return_value=False):
                app.media_inspect_button.invoke();root.update()
            assert app.store.media_inspection_history()==[]
            with patch('desktop.app.messagebox.askyesno',return_value=True):
                app.media_inspect_button.invoke();root.update()
            assert '검사 #1' in app.media_feedback.get(),app.media_feedback.get()
            app._media_show_history();root.update()
            assert 'notes.txt' in app.media_feedback.get()
            app.sign_out();root.update()
            app._media_inspect_file()
            assert '거부' in app.media_feedback.get()
        finally:root.destroy()
    print('PASS Stage58 GUI: local choose, cancel, approve, history, logout denied')

if __name__=='__main__':main()
