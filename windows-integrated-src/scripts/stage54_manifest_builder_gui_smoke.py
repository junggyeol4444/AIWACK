"""Native Tkinter offline bundle manifest builder smoke (owner only)."""
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def deny(*args,**kwargs):
    raise AssertionError('Network forbidden')


def main():
    with patch.object(socket.socket,'connect',deny), \
         patch.object(socket.socket,'connect_ex',deny), \
         patch.object(socket.socket,'sendto',deny), \
         patch.object(socket.socket,'sendall',deny), \
         patch.object(socket,'getaddrinfo',deny):
        with tempfile.TemporaryDirectory(prefix='aiwack-manifest-builder-') as folder:
            p=Path(folder)
            file=p/'article.txt'
            file.write_text('Offline article text',encoding='utf-8')
            target=p/'batch.json'
            root=tk.Tk(); store=LocalStore(p/'company.sqlite3')
            try:
                app=AIWACKWindow(root,store)
                app.account_name.set('gui-builder-owner')
                app.account_password.set('gui-builder-password-2026')
                app.password_confirm.set('gui-builder-password-2026')
                app.auth_button.invoke(); root.update()
                assert store.is_authenticated
                assert app.research_bundle_manifest_button.winfo_exists()
                with patch('desktop.app.filedialog.askopenfilenames',return_value=(str(file),)), \
                     patch('desktop.app.simpledialog.askstring',side_effect=['https://example.org/article','Article']), \
                     patch('desktop.app.messagebox.askyesno',return_value=False):
                    app.research_bundle_manifest_button.invoke()
                assert not target.exists()
                assert not store.search_offline_research()
                with patch('desktop.app.filedialog.askopenfilenames',return_value=(str(file),)), \
                     patch('desktop.app.simpledialog.askstring',side_effect=['https://example.org/article','Article']), \
                     patch('desktop.app.messagebox.askyesno',return_value=True), \
                     patch('desktop.app.filedialog.asksaveasfilename',return_value=str(target)):
                    app.research_bundle_manifest_button.invoke()
                root.update()
                assert target.exists()
                assert '아직 SQLite 등록 없음' in app.research_feedback.get()
                assert not store.search_offline_research()
                with patch('desktop.app.filedialog.askopenfilenames',return_value=(str(file),)), \
                     patch('desktop.app.simpledialog.askstring',side_effect=['https://example.org/article','Article']), \
                     patch('desktop.app.messagebox.askyesno',return_value=True), \
                     patch('desktop.app.filedialog.asksaveasfilename',return_value=str(target)):
                    app.research_bundle_manifest_button.invoke()
                assert '덮어쓰지' in app.research_feedback.get()
                with patch('desktop.app.filedialog.askopenfilename',return_value=str(target)), \
                     patch('desktop.app.messagebox.askyesno',return_value=True):
                    app.research_bundle_button.invoke()
                root.update()
                assert len(store.search_offline_research())==1
                app.sign_out();root.update()
            finally:
                root.destroy()
    print('PASS: Tkinter manifest cancel, create, no overwrite, explicit import; sockets blocked')

if __name__=='__main__':main()
