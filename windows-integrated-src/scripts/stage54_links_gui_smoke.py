"""Real GUI button smoke test of passive HTML link inventory, no web access."""
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def _deny(*args, **kwargs):
    raise AssertionError('External network access prohibited')


def login(app, initial):
    app.account_name.set('links-gui-owner')
    app.account_password.set('links-gui-password-2026')
    if initial:
        app.password_confirm.set('links-gui-password-2026')
    app.auth_button.invoke()
    app.root.update()
    assert app.store.is_authenticated, app.auth_feedback.get()


def main():
    socket.socket.connect = _deny
    socket.socket.connect_ex = _deny
    socket.create_connection = _deny
    with tempfile.TemporaryDirectory(prefix='aiwack-links-') as folder:
        path = Path(folder) / 'company.sqlite3'
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(path))
            login(app, True)
            assert app.research_links_button.winfo_exists()
            app.research_url.set('https://example.org/root')
            app.research_title.set('sample HTML')
            app.research_kind.set('html_snapshot')
            app.research_content.insert('1.0',
               '<div>Text</div><a href="/next">Next</a><a href="javascript:evil()">Bad</a>')
            app.research_add_button.invoke()
            root.update()
            rows = app.research_tree.get_children()
            assert len(rows) == 1, len(rows)
            app.research_tree.selection_set(rows[0])
            app.research_tree.event_generate('<<TreeviewSelect>>')
            root.update()
            app.research_links_button.invoke()
            root.update()
            text = app.research_detail.get('1.0','end')
            assert 'https://example.org/next' in text, text
            assert 'javascript:' not in text, text
            assert '로컬 사본 없음' in text
            app.sign_out()
            root.update()
        finally:
            root.destroy()
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(path))
            login(app, False)
            rows = app.research_tree.get_children()
            assert len(rows) == 1
            app.research_tree.selection_set(rows[0])
            app.research_tree.event_generate('<<TreeviewSelect>>')
            root.update()
            app.research_links_button.invoke()
            root.update()
            assert 'https://example.org/next' in app.research_detail.get('1.0','end')
            print('PASS GUI link extraction, untrusted URL display, relogin persistence, no network')
        finally:
            root.destroy()


if __name__ == '__main__':
    main()
