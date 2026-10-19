"""Native Tkinter stage54 local-reference graph check with outbound sockets blocked."""
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def _deny(*args, **kwargs):
    raise AssertionError('network prohibited')


def login(app, first):
    app.account_name.set('trace-gui-owner')
    app.account_password.set('trace-gui-password-2026')
    if first:
        app.password_confirm.set('trace-gui-password-2026')
    app.auth_button.invoke()
    app.root.update()
    assert app.store.is_authenticated


def main():
    socket.socket.connect = _deny
    socket.socket.connect_ex = _deny
    socket.create_connection = _deny
    with tempfile.TemporaryDirectory(prefix='aiwack-trace-') as folder:
        db = Path(folder) / 'company.sqlite3'
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(db))
            login(app, True)
            assert app.research_trace_button.winfo_exists()
            app.research_url.set('https://example.org/a')
            app.research_title.set('first')
            app.research_kind.set('html_snapshot')
            app.research_content.insert('1.0','<p>Page A</p><a href="/b">B</a>')
            app.research_add_button.invoke()
            root.update()
            a = app.store.search_offline_research()[0]['id']
            b = app.store.add_offline_research('https://example.org/b','second','Text B')
            app._refresh_offline_research()
            rows = app.research_tree.get_children()
            selected = next(item for item in rows if int(app.research_tree.item(item,'values')[0]) == a)
            app.research_tree.selection_set(selected)
            app.research_tree.event_generate('<<TreeviewSelect>>')
            root.update()
            app.research_trace_button.invoke()
            root.update()
            display = app.research_detail.get('1.0','end')
            assert 'https://example.org/b' in display, display
            assert f'로컬 후보 #{b}' in display, display
            assert '미검증' in display
            app.sign_out()
            root.update()
        finally:
            root.destroy()
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(db))
            login(app, False)
            rows = app.research_tree.get_children()
            selected = next(item for item in rows if int(app.research_tree.item(item,'values')[0]) == a)
            app.research_tree.selection_set(selected)
            app.research_tree.event_generate('<<TreeviewSelect>>')
            root.update()
            app.research_trace_button.invoke()
            root.update()
            assert f'로컬 후보 #{b}' in app.research_detail.get('1.0','end')
            print('PASS real Tkinter reference trace + restart persistence + network denied')
        finally:
            root.destroy()


if __name__ == '__main__':
    main()
