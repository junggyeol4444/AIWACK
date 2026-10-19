"""Stage49 real Tkinter button flow: search, provenance, ACL preview, logout persistence."""
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    def blocked(*args,**kwargs): raise AssertionError('No network allowed')
    socket.socket.connect=blocked
    socket.socket.connect_ex=blocked
    with tempfile.TemporaryDirectory(prefix='aiwack49-') as tmp:
        dbpath=Path(tmp)/'aiwack.sqlite3'
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(dbpath))
            app.account_name.set('owner49')
            app.account_password.set('local-stage49-password')
            app.password_confirm.set('local-stage49-password')
            app.auth_button.invoke();root.update()
            assert app.store.is_authenticated
            employee=app.store.add_employee_draft('stage49_gui_staff','GUI 직원')
            other=app.store.add_employee_draft('stage49_gui_other','다른 직원')
            assert '회사 공동 지식 저장소' in app.quick_navigation['values']
            app.knowledge_title.set('안전 정책')
            app.knowledge_source.set('관리자 내부 문서')
            app.knowledge_content.insert('1.0','자금 지출은 별도 승인')
            app.knowledge_save_button.invoke();root.update()
            assert len(app.store.list_company_knowledge())==1,app.knowledge_feedback.get()
            doc=app.store.list_company_knowledge()[0]['id']
            app.knowledge_query.set('안전')
            app.knowledge_search_button.invoke();root.update()
            assert len(app.knowledge_tree.get_children())==1
            item=app.knowledge_tree.get_children()[0]
            app.knowledge_tree.selection_set(item);root.update()
            assert '자금 지출' in app.knowledge_details.get('1.0','end')
            app.knowledge_source_type.set('internal_record')
            app.knowledge_reference.set('회의록 52')
            app.knowledge_source_button.invoke();root.update()
            assert '출처 #1' in app.knowledge_feedback.get()
            assert len(app.store.list_company_knowledge_sources(doc))==1
            app.knowledge_employee.set(str(employee))
            app.knowledge_preview_button.invoke();root.update()
            assert '거부' in app.knowledge_feedback.get()
            app.knowledge_mode.set('restricted')
            app.knowledge_mode_button.invoke();root.update()
            assert app.store.read_company_knowledge_access(doc)['mode']=='restricted'
            app.knowledge_grant_button.invoke();root.update()
            assert app.store.preview_employee_knowledge_read(employee,doc)['title']=='안전 정책'
            app.knowledge_preview_button.invoke();root.update()
            assert '읽기 가능' in app.knowledge_feedback.get()
            assert app.store.preview_employee_knowledge_search(other)==[]
            app.knowledge_revoke_button.invoke();root.update()
            assert app.store.preview_employee_knowledge_search(employee)==[]
            app.knowledge_grant_button.invoke();root.update()
            app.knowledge_query.set('회의록 52')
            app.knowledge_search_button.invoke();root.update()
            assert len(app.knowledge_tree.get_children())==1
            app.sign_out();root.update()
            assert not app.store.is_authenticated
        finally:
            root.destroy()
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(dbpath))
            app.account_name.set('owner49')
            app.account_password.set('local-stage49-password')
            app.auth_button.invoke();root.update()
            assert app.store.preview_employee_knowledge_read(employee,doc)['content']=='자금 지출은 별도 승인'
            assert app.store.list_company_knowledge_sources(doc)[0]['reference']=='회의록 52'
            print('PASS Stage49: GUI search/provenance/ACL/preview and restart persistence')
        finally:root.destroy()


if __name__=='__main__':main()
