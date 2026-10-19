"""Native Tkinter manual follow-up queue check, including restart and denied sockets."""
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def deny(*args, **kwargs):
    raise AssertionError('network prohibited')


def login(app, first):
    app.account_name.set('followups-gui-owner')
    app.account_password.set('followups-gui-password-2026')
    if first:
        app.password_confirm.set('followups-gui-password-2026')
    app.auth_button.invoke()
    app.root.update()
    assert app.store.is_authenticated


def main():
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    socket.create_connection = deny
    with tempfile.TemporaryDirectory(prefix='aiwack-followups-') as folder:
        db = Path(folder) / 'company.sqlite3'
        for first in (True, False):
            root = tk.Tk()
            try:
                app = AIWACKWindow(root, LocalStore(db))
                login(app, first)
                assert app.research_followup_button.winfo_exists()
                if first:
                    app.store.add_offline_research('https://example.org/a', 'a',
                        '<p>local A</p><a href="/missing">M</a>', 'html_snapshot')
                app.research_followup_button.invoke()
                root.update()
                detail = app.research_detail.get('1.0', 'end')
                assert 'https://example.org/missing' in detail, detail
                assert '[로컬 미등록]' in detail, detail
                assert '출처 진위 미검증' in detail, detail
                assert '실제 인터넷 접속' in app.research_feedback.get()
                app.sign_out()
                root.update()
            finally:
                root.destroy()
    print('PASS native Tkinter offline follow-up queue + restart + blocked sockets')


if __name__ == '__main__':
    main()
