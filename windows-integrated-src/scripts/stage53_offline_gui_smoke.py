"""Actual Tkinter owner clicks for managed documents, with sockets disabled."""
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def forbid(*args,**kwargs):
    raise AssertionError('network operation attempted')


def login(app,first):
    app.account_name.set('stage53-owner')
    app.account_password.set('stage53-owner-password')
    if first:
        app.password_confirm.set('stage53-owner-password')
    app.auth_button.invoke()
    app.root.update()
    assert app.store.is_authenticated


def main():
    socket.socket.connect=forbid
    socket.socket.connect_ex=forbid
    socket.create_connection=forbid
    with tempfile.TemporaryDirectory(prefix='aiwack53-gui-') as temp:
        database=Path(temp)/'state.sqlite3'
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(database))
            login(app,True)
            assert '로컬 문서·파일 작업' in app.quick_navigation['values']
            app.document_name.set('meeting_notes.md')
            app.document_content.insert('1.0','최초 회의 기록')
            app.document_create_button.invoke();root.update()
            assert len(app.store.list_managed_documents())==1,app.document_feedback.get()
            assert (app.store.documents_dir/'meeting_notes.md').read_text('utf-8')=='최초 회의 기록'
            app.document_create_button.invoke();root.update()
            assert len(app.store.list_managed_documents())==1,'duplicate creation must be blocked'
            row=app.document_tree.get_children()[0]
            app.document_tree.selection_set(row);root.update()
            assert app.document_loaded_version==1,app.document_feedback.get()
            app.document_content.delete('1.0','end')
            app.document_content.insert('1.0','갱신된 회의 기록')
            app.document_update_button.invoke();root.update()
            assert app.document_loaded_version==2,app.document_feedback.get()
            assert (app.store.documents_dir/'meeting_notes.md').read_text('utf-8')=='갱신된 회의 기록'
            assert len(app.store.managed_document_revisions(1))==2
            app.document_content.delete('1.0','end')
            app.document_content.insert('1.0','다시 수정')
            app.document_loaded_version=1
            app.document_update_button.invoke();root.update()
            assert '먼저' in app.document_feedback.get(),app.document_feedback.get()
            app.sign_out();root.update()
        finally:
            root.destroy()
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(database))
            login(app,False)
            assert app.store.read_managed_document(1)['content']=='갱신된 회의 기록'
            app.document_tree.selection_set(app.document_tree.get_children()[0]);root.update()
            assert app.document_loaded_version==2
            print('PASS Stage53: actual GUI create/duplicate/update/stale-version/relogin/SQLite and file persistence; sockets blocked')
        finally:
            root.destroy()


if __name__=='__main__': main()
