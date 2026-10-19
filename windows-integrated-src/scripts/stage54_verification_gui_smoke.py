"""Real Tkinter JSON verification button, restart, and blocked sockets."""
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def deny(*args, **kwargs):
    raise AssertionError('outbound socket forbidden')


def login(app, first):
    app.account_name.set('verify-gui-owner')
    app.account_password.set('verify-gui-password-2026')
    if first:
        app.password_confirm.set('verify-gui-password-2026')
    app.auth_button.invoke()
    app.root.update()
    assert app.store.is_authenticated


def main():
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    socket.create_connection = deny
    with tempfile.TemporaryDirectory(prefix='aiwack-verify-gui-') as folder:
        db = Path(folder) / 'local.sqlite3'
        path = Path(folder) / 'evidence.json'
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(db))
            login(app, True)
            app.store.add_offline_research('https://example.org/one', 'local', 'alpha evidence')
            app.store.export_local_research_evidence('alpha', path)
            assert app.research_verify_button.winfo_exists()
            with patch('desktop.app.filedialog.askopenfilename', return_value=str(path)):
                app.research_verify_button.invoke()
            root.update()
            assert '로컬 DB 일치' in app.research_feedback.get()
            assert '웹 출처·내용 진위 미검증' in app.research_detail.get('1.0', 'end')
            with patch('desktop.app.filedialog.askopenfilename', return_value=''):
                app.research_verify_button.invoke()
            assert '취소' in app.research_feedback.get()
            app.sign_out()
            root.update()
        finally:
            root.destroy()
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(db))
            login(app, False)
            with patch('desktop.app.filedialog.askopenfilename', return_value=str(path)):
                app.research_verify_button.invoke()
            root.update()
            assert '로컬 DB 일치' in app.research_feedback.get()
            app.store.add_offline_research('https://example.org/two', 'second', 'alpha new')
            with patch('desktop.app.filedialog.askopenfilename', return_value=str(path)):
                app.research_verify_button.invoke()
            root.update()
            assert '로컬 DB 불일치' in app.research_feedback.get()
            print('PASS Tkinter verification + mismatch + cancel + restart + blocked sockets')
        finally:
            root.destroy()

if __name__ == '__main__':
    main()
