"""Offline Tkinter audit/compare button smoke: no web or subprocess execution."""
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def denied(*args, **kwargs):
    raise AssertionError('Outbound network call blocked')


def auth(app, initial):
    app.account_name.set('audit-gui-owner')
    app.account_password.set('audit-gui-owner-password')
    if initial:
        app.password_confirm.set('audit-gui-owner-password')
    app.auth_button.invoke()
    app.root.update()
    assert app.store.is_authenticated, app.auth_feedback.get()


def main():
    socket.socket.connect=denied
    socket.socket.connect_ex=denied
    socket.create_connection=denied
    with tempfile.TemporaryDirectory(prefix='aiwack-audit-gui-') as folder:
        db=Path(folder)/'company.sqlite3'
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(db))
            auth(app,True)
            assert app.research_audit_button.winfo_exists()
            assert app.research_compare_button.winfo_exists()
            app.research_url.set('https://example.org/report1')
            app.research_title.set('First report')
            app.research_content.insert('1.0','Offline evidence')
            app.research_add_button.invoke()
            root.update()
            assert len(app.research_tree.get_children())==1
            app.research_url.set('https://example.org/report2')
            app.research_title.set('Second report')
            app.research_content.delete('1.0','end')
            app.research_content.insert('1.0','Offline evidence')
            app.research_add_button.invoke()
            root.update()
            assert len(app.research_tree.get_children())==2
            app.research_audit_button.invoke()
            root.update()
            assert '불일치: 0건' in app.research_detail.get('1.0','end')
            assert '검사 완료' in app.research_feedback.get()
            first=app.research_tree.get_children()[0]
            id1=int(app.research_tree.item(first,'values')[0])
            app.research_tree.selection_set(first)
            app.research_tree.event_generate('<<TreeviewSelect>>')
            root.update()
            app.research_compare_id.set(str(1 if id1!=1 else 2))
            app.research_compare_button.invoke()
            root.update()
            comparison=app.research_detail.get('1.0','end')
            assert '본문 일치: 예' in comparison,comparison
            assert '기재된 출처 URL 일치: 아니오' in comparison,comparison
            assert '웹사이트' in comparison
            app.sign_out()
            root.update()
        finally:
            root.destroy()
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(db))
            auth(app,False)
            app.research_audit_button.invoke()
            root.update()
            assert '자료 2건' in app.research_detail.get('1.0','end')
            assert len(app.research_tree.get_children())==2
            print('PASS offline GUI audit, evidence comparison, logout/login persistence, blocked network')
        finally:
            root.destroy()


if __name__=='__main__':
    main()
