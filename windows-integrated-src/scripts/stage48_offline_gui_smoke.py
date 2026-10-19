"""Real Tkinter GUI button flow and durable SQLite records, no internet."""
import socket
import sys
import tempfile
from pathlib import Path
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    def blocked(*args,**kwargs):raise AssertionError('No network allowed')
    socket.socket.connect=blocked
    socket.socket.connect_ex=blocked
    with tempfile.TemporaryDirectory(prefix='aiwack48-') as temp:
        dbpath=Path(temp)/'company.sqlite3'
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(dbpath))
            app.account_name.set('owner48')
            app.account_password.set('local-stage48-password')
            app.password_confirm.set('local-stage48-password')
            app.auth_button.invoke();root.update()
            assert app.store.is_authenticated
            assert '회사 공동 지식 저장소' in app.quick_navigation['values']
            app.knowledge_kind.set('policy')
            app.knowledge_title.set('운영 지침')
            app.knowledge_source.set('관리자 문서')
            app.knowledge_content.insert('1.0','외부 지출은 별도 승인')
            app.knowledge_save_button.invoke();root.update()
            documents=app.store.list_company_knowledge()
            assert len(documents)==1,app.knowledge_feedback.get()
            did=documents[0]['id']
            app.knowledge_refresh_button.invoke();root.update()
            item=app.knowledge_tree.get_children()[0]
            app.knowledge_tree.selection_set(item);root.update()
            assert '외부 지출' in app.knowledge_details.get('1.0','end')
            app.knowledge_archive_button.invoke();root.update()
            assert not app.knowledge_tree.get_children()
            assert app.store.read_company_knowledge(did)['archived_at']
            app.sign_out();root.update()
            assert not app.store.is_authenticated
        finally:
            root.destroy()
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(dbpath))
            app.account_name.set('owner48')
            app.account_password.set('local-stage48-password')
            app.auth_button.invoke();root.update()
            assert app.store.read_company_knowledge(did)['content']=='외부 지출은 별도 승인'
            print('PASS Stage48 offline GUI: create/view/archive, logout/login durability')
        finally:root.destroy()


if __name__=='__main__':main()
