"""Native Tkinter owner-only follow-up JSON recheck; run under Xvfb."""
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
    raise AssertionError('network forbidden')


def login(app, first):
    app.account_name.set('recheck-gui-owner')
    app.account_password.set('recheck-gui-password-2026')
    if first:
        app.password_confirm.set('recheck-gui-password-2026')
    app.auth_button.invoke()
    app.root.update()
    assert app.store.is_authenticated


def check_button(app, path, expected):
    assert app.research_followup_verify_button.winfo_exists()
    with patch('desktop.app.filedialog.askopenfilename', return_value=str(path)):
        app.research_followup_verify_button.invoke()
    app.root.update()
    assert expected in app.research_feedback.get(), app.research_feedback.get()
    assert '웹 접속 없음' in app.research_detail.get('1.0', 'end')


def main():
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    socket.create_connection = deny
    with tempfile.TemporaryDirectory(prefix='aiwack-followup-recheck-') as folder:
        db = Path(folder) / 'owner.sqlite3'
        path = Path(folder) / 'followups.json'
        for first in (True, False):
            root = tk.Tk()
            try:
                app = AIWACKWindow(root, LocalStore(db))
                login(app, first)
                if first:
                    app.store.add_offline_research('https://example.org/index', 'Local HTML',
                        '<a href="/missing">M</a>', 'html_snapshot')
                    app.store.export_offline_research_followups(path)
                check_button(app, path, '로컬 DB 일치')
                if not first:
                    app.store.record_offline_research_followup_note(
                        'https://example.org/missing', 'deferred', 'Check later')
                    check_button(app, path, '로컬 DB 불일치')
                    assert '기록·상태 변경 (1)' in app.research_detail.get('1.0', 'end')
                with patch('desktop.app.filedialog.askopenfilename', return_value=''):
                    app.research_followup_verify_button.invoke()
                assert '취소' in app.research_feedback.get()
                app.sign_out()
                root.update()
            finally:
                root.destroy()
    print('PASS native Tkinter follow-up JSON recheck + drift + cancel + restart + sockets blocked')


if __name__ == '__main__':
    main()
