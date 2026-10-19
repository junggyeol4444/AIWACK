"""Native Tkinter URL warning triage, with Python network calls disabled."""
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def deny(*args, **kwargs):
    raise AssertionError('Network is forbidden')


def main():
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    socket.create_connection = deny
    socket.getaddrinfo = deny
    with tempfile.TemporaryDirectory(prefix='aiwack-url-preflight-') as folder:
        path = Path(folder) / 'owner.sqlite3'
        for first in (True, False):
            root = tk.Tk()
            try:
                app = AIWACKWindow(root, LocalStore(path))
                app.account_name.set('preflight-owner')
                app.account_password.set('preflight-password-2026')
                if first:
                    app.password_confirm.set('preflight-password-2026')
                app.auth_button.invoke()
                root.update()
                assert app.store.is_authenticated
                if first:
                    app.store.add_offline_research(
                        'https://origin.example/index', 'Offline snapshot',
                        '<a href="http://169.254.169.254/private">metadata</a>'
                        '<a href="https://public.example/ok">normal</a>',
                        'html_snapshot')
                assert app.research_url_preflight_button.winfo_exists()
                app.research_url_preflight_button.invoke()
                root.update()
                content = app.research_detail.get('1.0', 'end')
                assert '169.254.169.254' in content, content
                assert 'non_global_ip_literal' in content
                assert '경고 URL 1개' in content
                assert '안전한 웹 주소라는 뜻이 아닙니다' in content
                assert 'DNS/웹 접속 없음' in app.research_feedback.get()
                if not first:
                    app.store.record_offline_research_followup_note(
                        'http://169.254.169.254/private', 'deferred', 'Manual later')
                    app.research_review_filter.set('pending')
                    app.research_url_preflight_button.invoke()
                    root.update()
                    content = app.research_detail.get('1.0', 'end')
                    assert '경고 URL 0개' in content, content
                app.sign_out()
                root.update()
            finally:
                root.destroy()
    print('PASS native Tkinter URL preflight + filter + relogin + socket blocking')


if __name__ == '__main__':
    main()
