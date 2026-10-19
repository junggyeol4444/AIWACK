"""Stage50 actual native Tk buttons in blocked-network Linux display, SQLite restart."""
import socket
import sys
import tempfile
from pathlib import Path
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def blocked(*args,**kwargs):
    raise AssertionError('No network connection is allowed in this smoke test')


def main():
    socket.socket.connect=blocked
    socket.socket.connect_ex=blocked
    with tempfile.TemporaryDirectory(prefix='aiwack50-') as tmp:
        path=Path(tmp)/'company.sqlite3'
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(path))
            app.account_name.set('stage50-owner')
            app.account_password.set('stage50-secure-local-password')
            app.password_confirm.set('stage50-secure-local-password')
            app.auth_button.invoke();root.update()
            assert app.store.is_authenticated
            assert '성과 평가·업무 개선' in app.quick_navigation['values']
            task=app.store.add_task('완료한 업무')
            app.store.set_task_status(task,'in_progress')
            app.store.set_task_status(task,'done')
            app.performance_task_id.set(str(task))
            app.performance_rating.set('4')
            app.performance_evidence.set('로컬 테스트 로그 확인')
            app.performance_lesson.set('QA 절차 문서화 필요')
            app.performance_review_button.invoke();root.update()
            reviews=app.store.list_task_performance_reviews()
            assert len(reviews)==1 and reviews[0]['rating']==4,app.performance_feedback.get()
            app.improvement_title.set('문서화 개선')
            app.improvement_action.set('QA 체크리스트 초안 작성')
            app.improvement_expected.set('누락 감소 예상, 아직 검증되지 않음')
            app.improvement_create_button.invoke();root.update()
            proposals=app.store.list_task_improvements()
            assert len(proposals)==1,app.performance_feedback.get()
            item=app.performance_proposals_tree.get_children()[0]
            app.performance_proposals_tree.selection_set(item)
            app.improvement_reason.set('관리자가 근거를 검토함')
            app.improvement_accept_button.invoke();root.update()
            assert app.store.list_task_improvements()[0]['state']=='accepted',app.performance_feedback.get()
            assert len(app.store.list_tasks())==1,'Proposal cannot create task or trigger AI'
            app.sign_out();root.update()
            assert not app.store.is_authenticated
        finally:
            root.destroy()
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(path))
            app.account_name.set('stage50-owner')
            app.account_password.set('stage50-secure-local-password')
            app.auth_button.invoke();root.update()
            assert len(app.store.list_task_performance_reviews())==1
            assert app.store.list_task_improvements()[0]['decision_reason']=='관리자가 근거를 검토함'
            assert '수동 평가 1건' in app.performance_summary.get()
            print('PASS Stage50: actual GUI buttons, decisions, network blocked, SQLite restart')
        finally:
            root.destroy()


if __name__=='__main__':main()
