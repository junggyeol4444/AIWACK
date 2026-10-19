"""Actual native Tkinter owner-only host triage, offline under Xvfb."""
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def deny(*args, **kwargs):
    raise AssertionError('network access forbidden')


def main():
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    socket.create_connection = deny
    socket.getaddrinfo = deny
    with tempfile.TemporaryDirectory(prefix='aiwack-host-triage-') as folder:
        path = Path(folder) / 'owner.sqlite3'
        for first in (True, False):
            root = tk.Tk()
            try:
                app = AIWACKWindow(root, LocalStore(path))
                app.account_name.set('domain-owner')
                app.account_password.set('domain-password-2026')
                if first:
                    app.password_confirm.set('domain-password-2026')
                app.auth_button.invoke()
                root.update()
                assert app.store.is_authenticated
                if first:
                    app.store.add_offline_research(
                        'https://origin.example/index', 'Offline snapshot',
                        '<a href="https://alpha.example/a">A</a>'
                        '<a href="https://alpha.example/b">B</a>'
                        '<a href="https://beta.example/c">C</a>', 'html_snapshot')
                assert app.research_followup_domains_button.winfo_exists()
                app.research_followup_domains_button.invoke()
                root.update()
                content = app.research_detail.get('1.0', 'end')
                assert '[alpha.example] URL 2' in content, content
                assert '[beta.example] URL 1' in content, content
                assert '출처 진위 미검증' in content
                assert '웹 접속' in app.research_feedback.get()
                if not first:
                    app.store.record_offline_research_followup_note(
                        'https://alpha.example/a', 'deferred', 'review later')
                    app.research_review_filter.set('deferred')
                    app.research_followup_domains_button.invoke()
                    root.update()
                    content = app.research_detail.get('1.0', 'end')
                    assert '[alpha.example] URL 1' in content
                    assert '[beta.example]' not in content
                app.sign_out()
                root.update()
            finally:
                root.destroy()
    print('PASS native Tkinter hostname summary + manual filter + relogin + sockets blocked')


if __name__ == '__main__':
    main()
