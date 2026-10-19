"""Tkinter real widget actions for the Stage54 offline-only research register."""
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore

def forbidden(*args,**kwargs):
    raise AssertionError('unexpected network operation')

def login(app, first):
    app.account_name.set('stage54-owner')
    app.account_password.set('stage54-secure-password')
    if first:app.password_confirm.set('stage54-secure-password')
    app.auth_button.invoke();app.root.update()
    assert app.store.is_authenticated,app.auth_feedback.get()

def main():
    socket.socket.connect=forbidden
    socket.socket.connect_ex=forbidden
    socket.create_connection=forbidden
    with tempfile.TemporaryDirectory(prefix='aiwack54-gui-') as folder:
        db=Path(folder)/'company.sqlite3'
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(db));login(app,True)
            assert '오프라인 조사 자료 수집' in app.quick_navigation['values']
            app.research_url.set('https://example.org/market')
            app.research_title.set('수동 확보 보고서')
            app.research_kind.set('html_snapshot')
            app.research_content.insert('1.0','<h1>한국어 시장 분석</h1><script>alert(1)</script><p>요약 내용</p>')
            app.research_add_button.invoke();root.update()
            assert len(app.store.search_offline_research())==1,app.research_feedback.get()
            app.research_add_button.invoke();root.update()
            assert len(app.store.search_offline_research())==1
            app.research_query.set('한국어')
            app.research_search_button.invoke();root.update()
            assert len(app.research_tree.get_children())==1
            row=app.research_tree.get_children()[0]
            app.research_tree.selection_set(row);root.update()
            assert app.research_selected_id==1
            detail=app.research_detail.get('1.0','end')
            assert '시장 분석' in detail and 'alert' not in detail
            app.research_archive_button.invoke();root.update()
            assert app.store.search_offline_research()==[]
            app.sign_out();root.update()
        finally:
            root.destroy()
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(db));login(app,False)
            app.research_include_archived.set(True)
            app.research_search_button.invoke();root.update()
            assert len(app.research_tree.get_children())==1
            assert app.store.read_offline_research(1)['archived_at']
            print('PASS Stage54 offline GUI: add, duplicate reject, literal search, detail, archive, restart; sockets blocked')
        finally:
            root.destroy()

if __name__=='__main__':main()
