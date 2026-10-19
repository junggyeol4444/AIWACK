"""Native Tkinter owner-only overlap report; no sockets or external files."""
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def deny(*args, **kwargs):
    raise AssertionError('network forbidden')


def main():
    for attr in ('connect', 'connect_ex', 'sendto', 'sendall'):
        setattr(socket.socket, attr, deny)
    socket.getaddrinfo = deny
    with tempfile.TemporaryDirectory(prefix='aiwack-overlap-') as folder:
        path = Path(folder) / 'owner.sqlite3'
        for first in (True, False):
            root = tk.Tk()
            try:
                app = AIWACKWindow(root, LocalStore(path))
                app.account_name.set('overlap-owner')
                app.account_password.set('long-password-2026')
                if first:
                    app.password_confirm.set('long-password-2026')
                app.auth_button.invoke()
                root.update()
                assert app.store.is_authenticated
                if first:
                    app.store.add_offline_research('https://a.example/a', 'A', 'same local body')
                    app.store.add_offline_research('https://b.example/b', 'B', 'same local body')
                    app.store.add_offline_research('https://a.example/a', 'A2', 'changed local body')
                assert app.research_source_overlap_button.winfo_exists()
                app.research_source_overlap_button.invoke()
                root.update()
                content = app.research_detail.get('1.0', 'end')
                assert '동일 본문·서로 다른 URL 1그룹' in content, content
                assert '동일 URL·본문 차이 1그룹' in content, content
                assert '외부 접속/진위 검증 없음' in app.research_feedback.get()
                app.sign_out()
                root.update()
            finally:
                root.destroy()
    print('PASS native Tkinter overlap grouping + relogin + socket blocking')


if __name__ == '__main__':
    main()
