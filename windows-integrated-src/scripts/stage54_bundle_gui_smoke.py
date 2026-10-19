"""Native Tkinter owner-only batch import smoke under blocked sockets; no HTTP requests."""
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def forbidden(*args, **kwargs):
    raise AssertionError('Network attempted')


def login(app, setup):
    app.account_name.set('bundle-smoke-owner')
    app.account_password.set('bundle-smoke-password-2026')
    if setup:
        app.password_confirm.set('bundle-smoke-password-2026')
    app.auth_button.invoke()
    app.root.update()
    assert app.store.is_authenticated, app.auth_feedback.get()


def main():
    socket.socket.connect = forbidden
    socket.socket.connect_ex = forbidden
    socket.create_connection = forbidden
    with tempfile.TemporaryDirectory(prefix='aiwack54-bundle-') as folder:
        root_path=Path(folder)
        database=root_path/'db.sqlite3'
        (root_path/'page.html').write_text('<h1>Stored page</h1><script>bad()</script>',encoding='utf-8')
        (root_path/'notice.txt').write_text('Second offline notice',encoding='utf-8')
        manifest=root_path/'manifest.json'
        manifest.write_text(json.dumps({'format':'aiwack-offline-research-bundle-v1','items':[
            {'file':'page.html','url':'https://example.org/page','title':'Local page'},
            {'file':'notice.txt','url':'https://example.org/notice','title':'Local notice'}]}),encoding='utf-8')
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(database))
            login(app,True)
            with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                    patch('desktop.app.messagebox.askyesno', return_value=True):
                app.research_bundle_button.invoke()
            root.update()
            assert '2건 등록' in app.research_feedback.get(),app.research_feedback.get()
            assert len(app.research_tree.get_children())==2
            for node in app.research_tree.get_children():
                app.research_tree.selection_set(node)
                app.research_tree.event_generate('<<TreeviewSelect>>')
                root.update()
                detail=app.research_detail.get('1.0','end')
                assert '목록 SHA-256' in detail
                assert hashlib.sha256(manifest.read_bytes()).hexdigest() in detail
                assert 'bad()' not in detail
            with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)):
                app.research_bundle_button.invoke()
            root.update()
            assert '가져오기 차단' in app.research_feedback.get(),app.research_feedback.get()
            assert len(app.research_tree.get_children())==2
            app.sign_out();root.update()
        finally:
            root.destroy()
        root=tk.Tk()
        try:
            app=AIWACKWindow(root, LocalStore(database))
            login(app,False)
            assert len(app.research_tree.get_children())==2
            assert app.store.read_offline_research(1)['bundle_import']['item_count']==2
            print('PASS batch GUI import, provenance, duplicate rollback, restart, blocked sockets')
        finally:
            root.destroy()

if __name__=='__main__':
    main()
