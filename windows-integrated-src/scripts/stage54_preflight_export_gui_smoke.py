"""Native Tkinter owner-driven warning JSON export/recheck, sockets blocked."""
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
    raise AssertionError('Network forbidden')


def main():
    for attr in ('connect', 'connect_ex', 'sendto', 'sendall'):
        setattr(socket.socket, attr, deny)
    socket.getaddrinfo = deny
    with tempfile.TemporaryDirectory(prefix='aiwack-preflight-export-') as folder:
        db = Path(folder) / 'local.sqlite3'
        output = Path(folder) / 'warnings.json'
        for first in (True, False):
            root = tk.Tk()
            try:
                app = AIWACKWindow(root, LocalStore(db))
                app.account_name.set('export-owner')
                app.account_password.set('long-password-2026')
                if first:
                    app.password_confirm.set('long-password-2026')
                app.auth_button.invoke()
                root.update()
                assert app.store.is_authenticated
                if first:
                    app.store.add_offline_research(
                        'https://origin.example/index', 'Local HTML',
                        '<a href="https://127.0.0.1/private">warning</a>', 'html_snapshot')
                    with patch('desktop.app.filedialog.asksaveasfilename', return_value=str(output)):
                        app.research_url_preflight_export_button.invoke()
                    root.update()
                    assert output.is_file()
                    assert 'URL 경고 JSON 저장:' in app.research_feedback.get()
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(output)):
                    app.research_url_preflight_verify_button.invoke()
                root.update()
                detail = app.research_detail.get('1.0', 'end')
                assert '현재 로컬 DB 경고 목록 일치: 예' in detail, detail
                assert '전자서명' in detail
                assert '로컬 DB 일치' in app.research_feedback.get()
                if not first:
                    app.store.add_offline_research(
                        'https://new.example/index', 'Local HTML 2',
                        '<a href="https://machine.local/new">warning</a>', 'html_snapshot')
                    with patch('desktop.app.filedialog.askopenfilename', return_value=str(output)):
                        app.research_url_preflight_verify_button.invoke()
                    root.update()
                    assert '현재 로컬 DB 경고 목록 일치: 아니오' in app.research_detail.get('1.0', 'end')
                app.sign_out()
                root.update()
            finally:
                root.destroy()
    print('PASS native Tkinter warning JSON export + recheck + drift + relogin, sockets blocked')


if __name__ == '__main__':
    main()
