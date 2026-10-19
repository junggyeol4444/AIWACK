"""Real Tkinter Stage46 button verification with socket outbound connections denied."""
import socket
import sys
import tempfile
from pathlib import Path
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def forbidden(*args, **kwargs):
    raise AssertionError('Network calls are not allowed during Stage46 smoke')


def main():
    socket.socket.connect=forbidden
    socket.socket.connect_ex=forbidden
    with tempfile.TemporaryDirectory(prefix='aiwack46-') as directory:
        path=Path(directory)/'company.sqlite3'
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(path))
            app.account_name.set('owner-gui-46')
            app.account_password.set('stage46-strong-local-password')
            app.password_confirm.set('stage46-strong-local-password')
            app.auth_button.invoke()
            root.update()
            assert app.store.is_authenticated
            assert 'AI 회의 결정·후속 업무' in app.quick_navigation['values']
            dep=app.store.add_department('기획팀')
            people=[app.store.add_employee_draft(f'worker46_{i}',f'직원 {i}',department_id=dep) for i in range(3)]
            app.meeting_title.set('출시 회의')
            app.meeting_create_button.invoke()
            meeting=int(app.meeting_id.get())
            app.meeting_topic.set('출시 의사결정')
            app.meeting_topic_button.invoke()
            for worker in people[:2]:
                app.meeting_employee.set(str(worker))
                app.meeting_add_button.invoke()
            app.meeting_schedule_button.invoke()
            assert app.store.read_meeting(meeting)['status']=='scheduled'
            agenda=app.store.read_meeting(meeting)['agenda'][0]['id']
            app.opinion_meeting_id.set(str(meeting))
            app.opinion_agenda_id.set(str(agenda))
            app.opinion_employee_id.set(str(people[0]))
            app.opinion_stance.set('찬성')
            app.opinion_reason.set('절차 필요')
            app.opinion_submit_button.invoke()
            app.decision_meeting_id.set(str(meeting))
            app.decision_agenda_id.set(str(agenda))
            app.decision_outcome.set('approved')
            app.decision_rationale.set('기획 검토 후 내부 점검 수행')
            app.decision_save_button.invoke()
            assert '확인' in app.decision_feedback.get(),app.decision_feedback.get()
            assert not app.store.list_meeting_decisions(meeting)
            app.decision_acknowledge.set(True)
            app.decision_save_button.invoke()
            root.update()
            rows=app.store.list_meeting_decisions(meeting)
            assert len(rows)==1 and rows[0]['missing_count']==1
            decision=rows[0]['id']
            app.decision_employee.set(str(people[0]))
            app.decision_task_title.set('로컬 출시 점검표 작성')
            app.decision_task_description.set('결제나 외부 전송 없이 검토')
            app.decision_followup_button.invoke()
            root.update()
            task=app.store.list_meeting_decisions(meeting)[0]['task_id']
            assert task is not None,app.decision_feedback.get()
            assert app.store.read_task(task)['status']=='todo'
            assert app.store.read_task_routing(task)['employee_id']==people[0]
            app.decision_id.set(str(decision))
            app.decision_followup_button.invoke()
            assert '이미' in app.decision_feedback.get(),app.decision_feedback.get()
            assert len(app.store.list_tasks())==1
            app.decision_meeting_id.set('999999')
            app.decision_refresh_button.invoke()
            assert not app.decision_tree.get_children()
            assert not app.decision_id.get()
            app.sign_out()
            root.update()
            assert not app.store.is_authenticated
        finally:
            root.destroy()
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(path))
            app.account_name.set('owner-gui-46')
            app.account_password.set('stage46-strong-local-password')
            app.auth_button.invoke()
            root.update()
            assert app.store.list_meeting_decisions(meeting)[0]['task_id']==task
            app.decision_meeting_id.set(str(meeting))
            app.decision_refresh_button.invoke()
            assert len(app.decision_tree.get_children())==1
            print('PASS Stage46: offline Tkinter owner decision, acknowledgement guard, follow-up assignment, duplicate guard, relogin persistence')
        finally:
            root.destroy()


if __name__=='__main__':main()
