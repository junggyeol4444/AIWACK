"""Physical user mouse test for chief follow-up report and owner decision GUI.

The report is seeded with an explicitly SYNTHETIC string to isolate the
button/visibility/approval screen. Real native model subprocess coverage is
performed separately in the Windows integration task.
"""
from __future__ import annotations
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
from desktop import task_runtime


def find_button(parent, name):
    for w in parent.winfo_children():
        if isinstance(w, tk.Button) and w.cget('text') == name:
            return w
        match=find_button(w,name)
        if match is not None: return match
    return None


def click(root, widget):
    root.update()
    assert widget is not None and widget.winfo_viewable(), 'Visible GUI control required'
    pyautogui.click(widget.winfo_rootx()+widget.winfo_width()//2,
                    widget.winfo_rooty()+widget.winfo_height()//2)
    root.update()


def main():
    pyautogui.PAUSE=.12
    with tempfile.TemporaryDirectory(prefix='aiwack-chief-report-mouse-') as directory:
        store=LocalStore(Path(directory)/'company.sqlite3')
        store.setup_owner('chief_report_gui','chief-report-owner-password-2026')
        chief=store.add_employee_draft('chief_report_c','총괄 AI 시험 계정')
        worker=store.add_employee_draft('chief_report_w','직원 AI 시험 계정')
        store.assign_reporting_line(chief,'ceo')
        model=store.add_local_model(ModelConfig('SYNTHETIC test config',
                                               'llamafile',sys.executable,'',25))
        store.set_employee_model(chief,model)
        store.set_employee_model(worker,model)
        task=ops.create_task(store,'Chief-to-worker-and-chief-report mouse acceptance')
        ops.assign_task(store,task)
        ops.approve_chief_order(store,task,'SYNTHETIC approved work instruction')
        saved=task_runtime.run_local_model
        task_runtime.run_local_model=lambda *a,**kw:'SYNTHETIC STAFF OUTPUT FOR GUI TEST'
        try:
            artifact=ops.execute_task(store,task)['artifact_id']
        finally:
            task_runtime.run_local_model=saved
        report=store.save_chief_task_report(artifact,
                'SYNTHETIC CHIEF REVIEW FOR BUTTON-ONLY SCREEN TEST')
        root=tk.Tk()
        try:
            root.geometry('1120x850+15+15')
            app=AIWACKWindow(root,store)
            app.account_name.set('chief_report_gui')
            app.account_password.set('chief-report-owner-password-2026')
            app.submit_login()
            office=app.company_office
            office.refresh();office.set_view('results')
            office.artifact_list.selection_set(str(artifact))
            root.update()
            button=find_button(office.views['results'],'총괄 보고서 보기')
            click(root,button)
            dialog=next((c for c in root.winfo_children()
                        if isinstance(c,tk.Toplevel) and '총괄 AI 회수 보고서' in c.title()),None)
            assert dialog is not None and dialog.winfo_viewable()
            assert store.read_task(task)['status']=='in_progress'
            image=os.environ.get('AIWACK_CHIEF_REVIEW_SCREENSHOT')
            if image:
                output=Path(image)
                output.parent.mkdir(parents=True,exist_ok=True)
                pyautogui.screenshot().save(output)
            accept=find_button(dialog,'총괄 보고서 수락')
            orig=messagebox.askyesno
            messagebox.askyesno=lambda *a,**kw:True
            try:click(root,accept)
            finally:messagebox.askyesno=orig
            assert store.read_chief_task_report(report)['owner_decision']=='accepted'
            assert store.read_task_artifact(artifact)['review_status']=='pending'
            assert store.read_task(task)['status']=='in_progress'
            store.logout()
            reload=LocalStore(store.path)
            reload.login('chief_report_gui','chief-report-owner-password-2026')
            assert reload.read_chief_task_report(report)['owner_decision']=='accepted'
            assert reload.read_task(task)['status']=='in_progress'
            print('PHYSICAL_CHIEF_REVIEW_OWNER_ACCEPT_NO_AUTO_TASK_COMPLETION_PASS',flush=True)
        finally:
            if root.winfo_exists():root.destroy()

if __name__=='__main__':main()
