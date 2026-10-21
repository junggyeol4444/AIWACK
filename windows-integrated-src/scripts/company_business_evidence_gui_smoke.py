"""실제 Tk 버튼 + SQLite로 외부 증빙/실패 개선 전 과정을 검사한다. 서명은 시험용."""
import hashlib
import hmac
import json
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore
from desktop import company_operations as ops
from desktop.model_runtime import ModelConfig

def button(parent,text):
    for w in parent.winfo_children():
        if isinstance(w,tk.Button) and w.cget('text')==text:
            return w
        found=button(w,text)
        if found:return found
    return None

with tempfile.TemporaryDirectory() as folder:
    root=tk.Tk()
    old_confirm=messagebox.askyesno
    try:
        store=LocalStore(Path(folder)/'evidence-gui.sqlite3')
        ui=AIWACKWindow(root,store)
        ui.account_name.set('owner')
        ui.account_password.set('native-receipt-password-2026')
        ui.password_confirm.set('native-receipt-password-2026')
        ui.submit_setup()
        messagebox.askyesno=lambda *args,**kw:True
        business=store.create_business(1,'서명된 거래 검수 사업','수기 정산 증빙 대사')
        payload=json.dumps(dict(provider='fixture-provider',event_id='settle-0001',
            transaction_id='tx-0001',business_id=business,event_type='settlement',
            related_transaction='',currency='KRW',amount_minor=110000),sort_keys=True).encode()
        filename=Path(folder)/'payment.json'
        filename.write_bytes(payload)
        secret='fixture-provider-signing-secret-2026'
        signature=hmac.new(secret.encode(),payload,hashlib.sha256).hexdigest()
        for i in range(ui.tabs.index('end')):
            if ui.tabs.tab(i,'text')=='거래 증빙·실패 업무 개선':
                ui.tabs.select(i)
                break
        else:raise AssertionError('기존 프로그램 거래 증빙 탭 없음')
        root.update()
        ui.ev_payment_file.set(str(filename))
        ui.ev_signature.set(signature)
        ui.ev_secret.set(secret)
        b=button(root,'서명 검증·증빙 수신')
        assert b and b.winfo_viewable()
        b.invoke();root.update()
        assert len(store.list_signed_payment_events())==1
        ui.ev_event_id.set('1')
        ui.ev_review_note.set('관리자가 서명 확인 결과를 검수함')
        b=button(root,'증빙 수락')
        assert b and b.winfo_viewable()
        b.invoke();root.update()
        result=store.signed_payment_reconciliation_summary()
        assert result['accepted_signed_net_minor']==110000
        assert result['real_bank_settlement_confirmed'] is False
        origin=store.add_department('기존 직원 부서')
        target=store.add_department('성과 검수 부서')
        employee=store.add_employee_draft('failed_gui_staff','실패 검사 직원',department_id=origin)
        model=store.add_local_model(ModelConfig('fixture','llamafile',sys.executable,'',32))
        store.set_employee_model(employee,model)
        task=ops.create_task(store,'검수할 직원 실패 업무')
        ops.assign_task(store,task)
        import desktop.task_runtime as runtime
        old=runtime.run_local_model
        try:
            def fail(*args,**kw):raise RuntimeError('synthetic failure')
            runtime.run_local_model=fail
            try:ops.execute_task(store,task)
            except RuntimeError:pass
            else:raise AssertionError('실패 모델 증빙 미생성')
        finally:runtime.run_local_model=old
        b=button(root,'실제 실패 업무 개선 후보 검색')
        assert b and b.winfo_viewable()
        b.invoke();root.update()
        audit=store.failed_employee_followups()
        assert len(audit)==1
        ui.ev_followup_id.set(str(audit[0]['id']))
        b=button(root,'후속 업무 생성 승인')
        assert b and b.winfo_viewable()
        b.invoke();root.update()
        assert store.failed_employee_followups()[0]['followup_task_id'] is not None
        failed_run_id=store.list_task_runs(task)[0]['id']
        ui.reorg_staff.set(str(employee))
        ui.reorg_target.set(str(target))
        ui.reorg_run.set(str(failed_run_id))
        ui.reorg_reason.set('실제 모델 실패 원인 검토 후 소유자 조직 개편')
        for i in range(ui.tabs.index('end')):
            if ui.tabs.tab(i,'text')=='실제 직원 성과 기반 조직 개편':
                ui.tabs.select(i)
                break
        else:raise AssertionError('실제 조직 개편 GUI 탭 없음')
        root.update()
        b=button(root,'근거 기반 이동 제안')
        assert b and b.winfo_viewable()
        b.invoke();root.update()
        assert len(store.staff_department_transfer_audit())==1
        proposal=store.staff_department_transfer_audit()[0]
        ui.reorg_proposal.set(str(proposal['id']))
        b=button(root,'조직 이동 승인')
        assert b and b.winfo_viewable()
        b.invoke();root.update()
        assert store.read_employee_record(employee)['department_id']==target
        assert store.staff_department_transfer_audit()[0]['state']=='accepted'
        print('NATIVE_TK_FAILED_STAFF_REASSIGNMENT_OWNER_APPROVAL_PASS')
        print('NATIVE_TK_RECEIPT_RECONCILIATION_AND_REAL_FAILURE_FOLLOWUP_PASS')
        print('SYNTHETIC_SIGNATURE_NOT_REAL_PROVIDER_VERIFICATION')
    finally:
        messagebox.askyesno=old_confirm
        root.destroy()
