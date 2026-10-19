"""Offline Xvfb Tk button smoke for Stage44: no network connections and two logins."""
from __future__ import annotations
import socket
import sys
import tempfile
from pathlib import Path
import tkinter as tk
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.storage import LocalStore
from desktop.app import AIWACKWindow


def forbid_network(*args, **kwargs):
    raise RuntimeError('network connections prohibited during this test')


def main():
    socket.socket.connect = forbid_network
    socket.socket.connect_ex = forbid_network
    with tempfile.TemporaryDirectory(prefix='aiwack-stage44-gui-') as d:
        path=Path(d)/'offline.sqlite3'
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(path))
            root.update()
            assert not hasattr(app,'tabs')
            app.account_name.set('owner44gui')
            app.account_password.set('GUI-stage44-password-2026')
            app.password_confirm.set('GUI-stage44-password-2026')
            app.auth_button.invoke()
            root.update()
            assert app.store.is_authenticated
            assert 'AI 회의 안건·참석자' in app.quick_navigation['values']
            d1=app.store.add_department('연구부')
            d2=app.store.add_department('기획부')
            alice=app.store.add_employee_draft('gui44_alice','Alice',department_id=d1)
            bob=app.store.add_employee_draft('gui44_bob','Bob',department_id=d2)
            app.meeting_title.set('실제 GUI 회의')
            app.meeting_purpose.set('안건/참석 검증')
            app.meeting_create_button.invoke()
            root.update()
            mid=int(app.meeting_id.get())
            assert app.store.read_meeting(mid)['status']=='draft',app.meeting_feedback.get()
            app.meeting_topic.set('첫 회의 안건')
            app.meeting_topic_button.invoke()
            root.update()
            assert len(app.store.read_meeting(mid)['agenda'])==1
            app.meeting_schedule_button.invoke()  # invalid: no members
            root.update()
            assert app.store.read_meeting(mid)['status']=='draft'
            assert '참석자' in app.meeting_feedback.get()
            for person in (alice,bob):
                app.meeting_employee.set(str(person))
                app.meeting_add_button.invoke()
                root.update()
            assert len(app.store.read_meeting(mid)['attendees'])==2
            app.meeting_schedule_button.invoke()
            root.update()
            assert app.store.read_meeting(mid)['status']=='scheduled',app.meeting_feedback.get()
            assert len(app.meeting_detail_tree.get_children())==3
            app.meeting_topic.set('예약 후 무단 변경')
            app.meeting_topic_button.invoke()
            assert len(app.store.read_meeting(mid)['agenda'])==1
            app.meeting_cancel_button.invoke()
            assert app.store.read_meeting(mid)['status']=='cancelled'
            app.sign_out()
            root.update()
            assert not app.store.is_authenticated
        finally:
            root.destroy()
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(path))
            app.account_name.set('owner44gui')
            app.account_password.set('GUI-stage44-password-2026')
            app.auth_button.invoke()
            root.update()
            assert app.store.read_meeting(mid)['status']=='cancelled'
            assert app.store.read_meeting(mid)['agenda'][0]['topic']=='첫 회의 안건'
            assert len(app.store.read_meeting(mid)['attendees'])==2
            print('PASS stage44: offline Tk owner login, buttons, validation, roster, freeze, cancel and SQLite restart')
        finally:
            root.destroy()


if __name__=='__main__':
    main()
