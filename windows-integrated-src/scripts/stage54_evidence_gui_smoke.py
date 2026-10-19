"""Real Tkinter evidence search with outbound Python sockets blocked."""
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def deny(*args,**kwargs):
    raise AssertionError('network call forbidden')


def login(app, first):
    app.account_name.set('evidence-gui-owner')
    app.account_password.set('evidence-password-2026')
    if first:
        app.password_confirm.set('evidence-password-2026')
    app.auth_button.invoke()
    app.root.update()
    assert app.store.is_authenticated


def main():
    socket.socket.connect=deny
    socket.socket.connect_ex=deny
    socket.create_connection=deny
    with tempfile.TemporaryDirectory(prefix='aiwack-evidence-') as folder:
        db=Path(folder)/'local.sqlite3'
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(db))
            login(app,True)
            assert app.research_evidence_button.winfo_exists()
            record=app.store.add_offline_research('https://example.org/a','report','line one\nalpha finding')
            app.research_query.set('alpha')
            app.research_evidence_button.invoke()
            root.update()
            preview=app.research_detail.get('1.0','end')
            assert f'로컬 자료 #{record}' in preview
            assert '본문 2행: alpha finding' in preview
            assert '출처 URL(미검증)' in preview
            app.sign_out()
            root.update()
        finally:
            root.destroy()
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(db))
            login(app,False)
            app.research_query.set('alpha')
            app.research_evidence_button.invoke()
            root.update()
            assert f'로컬 자료 #{record}' in app.research_detail.get('1.0','end')
            print('PASS real Tkinter evidence report + restart + no outbound socket')
        finally:
            root.destroy()

if __name__=='__main__':
    main()
