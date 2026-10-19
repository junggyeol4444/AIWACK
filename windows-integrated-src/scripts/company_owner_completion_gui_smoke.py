"""Real Windows mouse owner-finalization GUI acceptance.
A synthetic model test double seeds one legitimate auditable result;
this tests GUI approval, not GGUF inference or EXE packaging.
"""
import os
import sys
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import pyautogui
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig
from desktop import company_operations as ops
import desktop.task_runtime as runtime

def button(widget,label):
    for child in widget.winfo_children():
        if isinstance(child,tk.Button) and child.cget('text')==label:return child
        b=button(child,label)
        if b is not None:return b
    return None

def click(root,widget):
    root.update()
    assert widget is not None and widget.winfo_viewable()
    pyautogui.click(widget.winfo_rootx()+widget.winfo_width()//2,
                    widget.winfo_rooty()+widget.winfo_height()//2)
    root.update()

def main():
    pyautogui.PAUSE=.12
    with tempfile.TemporaryDirectory(prefix='aiwack-owner-click-') as directory:
        root=tk.Tk()
        try:
            root.geometry('1040x720+20+20')
            store=LocalStore(Path(directory)/'company.sqlite3')
            app=AIWACKWindow(root,store)
            app.account_name.set('review_owner')
            app.account_password.set('owner-approved-password-2026')
            app.password_confirm.set('owner-approved-password-2026')
            app.submit_setup()
            employee=store.add_employee_draft('review_worker','검증 직원')
            model=store.add_local_model(ModelConfig('Synthetic UI fixture','llamafile',
                                                    str(Path(sys.executable).resolve()),'',24))
            store.set_employee_model(employee,model)
            tid=ops.create_task(store,'Owner approved final task')
            ops.assign_task(store,tid)
            original=runtime.run_local_model
            runtime.run_local_model=lambda *a,**kw:'SYNTHETIC TEST TEXT - NOT REAL GGUF'
            try:artifact=ops.execute_task(store,tid)['artifact_id']
            finally:runtime.run_local_model=original
            assert store.read_task(tid)['status']=='in_progress'
            store.review_task_artifact(artifact,'approved')
            office=app.company_office
            office.refresh()
            office.set_view('results')
            root.update()
            office.artifact_list.selection_set(str(artifact))
            old_events=len(store.list_task_status_events(tid))
            target=button(office.views['results'],'승인 결과로 업무 완료')
            yes=messagebox.askyesno
            messagebox.askyesno=lambda *a,**kw:True
            try:click(root,target)
            finally:messagebox.askyesno=yes
            assert store.read_task(tid)['status']=='done'
            assert len(store.list_task_status_events(tid))==old_events+1
            assert not ops.company_snapshot(store)['actual_sales_verified']
            if os.environ.get('AIWACK_OWNER_COMPLETE_SCREENSHOT'):
                dst=Path(os.environ['AIWACK_OWNER_COMPLETE_SCREENSHOT'])
                dst.parent.mkdir(parents=True,exist_ok=True)
                pyautogui.screenshot().save(dst)
            print('OWNER_REAL_MOUSE_COMPLETE_APPROVED_ARTIFACT_PASS',flush=True)
        finally:root.destroy()

if __name__=='__main__':main()
