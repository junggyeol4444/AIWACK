"""Stage45 real Tkinter input/buttons and SQLite persistence under blocked network."""
from __future__ import annotations
import socket
import sys
import tempfile
from pathlib import Path
import tkinter as tk
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.storage import LocalStore
from desktop.app import AIWACKWindow


def block(*args,**kwargs):
    raise RuntimeError('external connections prohibited')


def main():
    socket.socket.connect = block
    socket.socket.connect_ex = block
    with tempfile.TemporaryDirectory(prefix='aiwack-stage45-') as directory:
        path=Path(directory)/'company.sqlite3'
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(path))
            app.account_name.set('owner45-gui')
            app.account_password.set('stage45-offline-secure-password')
            app.password_confirm.set('stage45-offline-secure-password')
            app.auth_button.invoke()
            root.update()
            assert app.store.is_authenticated
            assert 'AI 회의 의견 수집·비교' in app.quick_navigation['values']
            dept=app.store.add_department('전략')
            people=[app.store.add_employee_draft('smoke45_'+str(i),'직원 '+str(i),department_id=dept) for i in range(3)]
            app.meeting_title.set('오프라인 회의')
            app.meeting_create_button.invoke()
            mid=int(app.meeting_id.get())
            app.meeting_topic.set('안건 확인')
            app.meeting_topic_button.invoke()
            for person in people[:2]:
                app.meeting_employee.set(str(person))
                app.meeting_add_button.invoke()
            app.meeting_schedule_button.invoke()
            root.update()
            assert app.store.read_meeting(mid)['status']=='scheduled',app.meeting_feedback.get()
            agenda=app.store.read_meeting(mid)['agenda'][0]['id']
            app.opinion_meeting_id.set(str(mid))
            app.opinion_agenda_id.set(str(agenda))
            app.opinion_employee_id.set(str(people[0]))
            app.opinion_stance.set('찬성')
            app.opinion_reason.set('첫 직원 의견')
            app.opinion_evidence.set('사내 기록')
            app.opinion_alternative.set('수정안')
            app.opinion_submit_button.invoke()
            root.update()
            assert len(app.store.list_meeting_opinions(mid))==1,app.opinion_feedback.get()
            app.opinion_employee_id.set(str(people[1]))
            app.opinion_stance.set('반대')
            app.opinion_reason.set('두 번째 의견')
            app.opinion_submit_button.invoke()
            root.update()
            assert len(app.opinion_comparison_tree.get_children())==1
            assert len(app.opinion_detail_tree.get_children())==2
            expected=app.store.compare_meeting_opinions(mid)['agenda'][0]
            assert expected['has_differing_opinions'] is True
            assert expected['counts']=={'찬성':1,'보류':0,'반대':1}
            assert len(expected['missing_attendees'])==0
            # Duplicate button must not erase or overwrite previous record.
            app.opinion_reason.set('변경 시도')
            app.opinion_submit_button.invoke()
            assert '이미' in app.opinion_feedback.get()
            assert len(app.store.list_meeting_opinions(mid))==2
            # Invalid meeting selection must clear previously displayed opinions.
            app.opinion_meeting_id.set('99999')
            app.opinion_refresh_button.invoke()
            assert not app.opinion_comparison_tree.get_children()
            assert not app.opinion_detail_tree.get_children()
            app.sign_out()
            root.update()
            assert not app.store.is_authenticated
        finally:
            root.destroy()
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(path))
            app.account_name.set('owner45-gui')
            app.account_password.set('stage45-offline-secure-password')
            app.auth_button.invoke()
            root.update()
            assert len(app.store.list_meeting_opinions(mid))==2
            app.opinion_meeting_id.set(str(mid))
            app.opinion_refresh_button.invoke()
            assert len(app.opinion_detail_tree.get_children())==2
            app.store.set_meeting_status(mid,'cancelled')
            app.opinion_agenda_id.set(str(agenda))
            app.opinion_employee_id.set(str(people[2]))
            app.opinion_reason.set('취소 후 입력 거절')
            app.opinion_submit_button.invoke()
            assert '예정' in app.opinion_feedback.get()
            print('PASS Stage45: offline Tk button actions, comparison, duplicate block, invalid selection cleared, relogin persistence, cancelled block')
        finally:
            root.destroy()


if __name__ == '__main__':
    main()
