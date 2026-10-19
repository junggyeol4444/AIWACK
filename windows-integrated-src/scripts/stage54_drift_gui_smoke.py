"""Real Tkinter drift detail display, restart, and offline-only socket guard."""
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
    app.account_name.set('drift-gui-owner')
    app.account_password.set('drift-gui-password-2026')
    if first:
        app.password_confirm.set('drift-gui-password-2026')
    app.auth_button.invoke()
    app.root.update()
    assert app.store.is_authenticated


def main():
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    socket.create_connection = deny
    with tempfile.TemporaryDirectory(prefix='aiwack-drift-gui-') as folder:
        db = Path(folder) / 'local.sqlite3'
        path = Path(folder) / 'evidence.json'
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(db))
            login(app, True)
            app.store.add_offline_research('https://example.org/one', 'local', 'alpha evidence')
            app.store.export_local_research_evidence('alpha', path)
            app.store.add_offline_research('https://example.org/two', 'second', 'alpha new')
            with patch('desktop.app.filedialog.askopenfilename', return_value=str(path)):
                app.research_verify_button.invoke()
            root.update()
            detail = app.research_detail.get('1.0', 'end')
            assert '로컬 DB 불일치' in app.research_feedback.get()
            assert '현재 DB에만 보이는 자료 ID: [2]' in detail
            assert '위 차이는 원인 진단이나 웹 출처 검증이 아닙니다.' in detail
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
            assert '현재 DB에만 보이는 자료 ID: [2]' in app.research_detail.get('1.0', 'end')
            print('PASS Tkinter drift ID details + restart + blocked sockets')
        finally:
            root.destroy()


if __name__ == '__main__':
    main()
