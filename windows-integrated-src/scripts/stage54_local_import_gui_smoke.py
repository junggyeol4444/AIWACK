"""Actual native Tkinter button smoke, offline-only Stage54 local file import."""
from pathlib import Path
import hashlib
import socket
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def offline(*args, **kwargs):
    raise AssertionError('A network call was attempted')


def login(app, initial):
    app.account_name.set('local-import-owner')
    app.account_password.set('secure-local-import-owner-password')
    if initial:
        app.password_confirm.set('secure-local-import-owner-password')
    app.auth_button.invoke()
    app.root.update()
    assert app.store.is_authenticated, app.auth_feedback.get()


def main():
    socket.socket.connect = offline
    socket.socket.connect_ex = offline
    socket.create_connection = offline
    with tempfile.TemporaryDirectory(prefix='aiwack54-import-gui-') as folder:
        db = Path(folder) / 'db.sqlite3'
        html = Path(folder) / 'saved-webpage.html'
        raw = b'<h1>Offline source</h1><script>alert(1)</script><p>Test report</p>'
        html.write_bytes(raw)
        root = tk.Tk()
        try:
            app = AIWACKWindow(root,LocalStore(db))
            login(app,True)
            app.research_url.set('https://example.org/pre-downloaded')
            app.research_title.set('Local HTML archive')
            with patch('desktop.app.filedialog.askopenfilename',return_value=str(html)):
                app.research_import_button.invoke()
            root.update()
            assert '로컬 파일 등록' in app.research_feedback.get(), app.research_feedback.get()
            assert len(app.research_tree.get_children()) == 1
            item = app.research_tree.get_children()[0]
            app.research_tree.selection_set(item)
            app.research_tree.event_generate('<<TreeviewSelect>>')
            root.update()
            assert app.research_selected_id == 1
            details = app.research_detail.get('1.0','end')
            assert '원본 바이트 SHA-256' in details
            assert hashlib.sha256(raw).hexdigest() in details
            assert 'Offline source' in details and 'alert(1)' not in details
            # Canceling the dialog must never insert a record.
            with patch('desktop.app.filedialog.askopenfilename',return_value=''):
                app.research_import_button.invoke()
            assert len(app.research_tree.get_children()) == 1
            # A duplicate must not insert either.
            with patch('desktop.app.filedialog.askopenfilename',return_value=str(html)):
                app.research_import_button.invoke()
            assert len(app.research_tree.get_children()) == 1
            assert '이미 등록' in app.research_feedback.get()
            app.sign_out();root.update()
        finally:
            root.destroy()
        root = tk.Tk()
        try:
            app = AIWACKWindow(root,LocalStore(db))
            login(app,False)
            app.research_search_button.invoke();root.update()
            assert len(app.research_tree.get_children()) == 1
            assert app.store.read_offline_research(1)['local_import']['raw_sha256'] == hashlib.sha256(raw).hexdigest()
            print('PASS local file GUI import, local hash, duplicate refusal, restart, sockets blocked')
        finally:
            root.destroy()


if __name__=='__main__':
    main()
