"""Real Tk button -> SQLite model audit; model response synthetic for GUI regression."""
import json
import tempfile
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig
from desktop import employee_model_runtime as runtime

with tempfile.TemporaryDirectory() as workdir:
    root=tk.Tk()
    original=runtime.run_local_model
    original_confirm=messagebox.askyesno
    try:
        store=LocalStore(Path(workdir)/'meeting-gui.sqlite3')
        ui=AIWACKWindow(root,store)
        ui.account_name.set('owner')
        ui.account_password.set('meeting-gui-password-2026')
        ui.password_confirm.set('meeting-gui-password-2026')
        ui.submit_setup()
        dept=store.add_department('기획')
        other=store.add_department('품질')
        worker=store.add_employee_draft('meeting_worker','회의 직원',department_id=dept)
        coworker=store.add_employee_draft('meeting_peer','동료 직원',department_id=other)
        exe=Path(workdir)/'test-model'
        exe.write_bytes(b'fixture')
        weights=Path(workdir)/'fake.gguf'
        weights.write_bytes(b'GGUF')
        mid=store.add_local_model(ModelConfig('gui-test-model','llama_cpp',str(exe),str(weights),64))
        store.set_employee_model(worker,mid)
        meeting=store.create_meeting('회의 모델 GUI','수기 입력과 다른 모델 출처')
        agenda=store.add_meeting_agenda(meeting,'결과 검수')
        for eid in (worker,coworker):
            store.add_meeting_attendee(meeting,eid)
        store.set_meeting_status(meeting,'scheduled')
        runtime.run_local_model=lambda *args,**kw:json.dumps(
            {'stance':'보류','reasoning':'실제 회의 모델 GUI 감사 검증'},ensure_ascii=False)
        messagebox.askyesno=lambda *args,**kw:True
        for i in range(ui.tabs.index('end')):
            if ui.tabs.tab(i,'text')=='AI 회의 의견 수집·비교':
                ui.tabs.select(i)
                break
        else:
            raise AssertionError('기존 회의 GUI 탭 없음')
        ui.opinion_meeting_id.set(str(meeting))
        ui.opinion_agenda_id.set(str(agenda))
        ui.opinion_employee_id.set(str(worker))
        root.update()
        button=ui.real_meeting_ai_button
        assert button.winfo_viewable()
        assert button.winfo_rooty()+button.winfo_height()<=root.winfo_rooty()+root.winfo_height()
        button.invoke()
        until=time.monotonic()+12
        while time.monotonic()<until:
            root.update()
            if store.real_meeting_opinion_audit(meeting) and '모델 감사' in ui.opinion_feedback.get():
                break
            time.sleep(.06)
        root.update()
        assert len(store.real_meeting_opinion_audit(meeting))==1
        assert '모델 감사' in ui.opinion_feedback.get()
        assert len(store.list_employee_model_calls(worker))==1
        assert not store.list_meeting_decisions(meeting)
        print('NATIVE_TK_REAL_MEETING_OPINION_BUTTON_SQLITE_AUDIT_PASS')
        print('MODEL_RESPONSE_SYNTHETIC_GUI_CHECK_ONLY')
    finally:
        runtime.run_local_model=original
        messagebox.askyesno=original_confirm
        root.destroy()
