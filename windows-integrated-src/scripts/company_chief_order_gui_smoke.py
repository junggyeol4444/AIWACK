"""Physical mouse owner-approval GUI test for chief→staff instruction handoff.

An inert synthetic draft seeds the modal. This tests only human approval and
no worker starts; real model subprocess coverage lives in separate tests.
"""
from __future__ import annotations

import os
import sys
import tempfile
import tkinter as tk
from pathlib import Path

import pyautogui
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig
from desktop import company_operations as ops


def find_button(container, label):
    for child in container.winfo_children():
        if isinstance(child, tk.Button) and child.cget('text') == label:
            return child
        child_button=find_button(child,label)
        if child_button is not None:
            return child_button
    return None


def click(root,widget):
    root.update()
    assert widget is not None and widget.winfo_viewable(), 'Expected a visible Windows/Tk button'
    pyautogui.click(widget.winfo_rootx()+widget.winfo_width()//2,
                    widget.winfo_rooty()+widget.winfo_height()//2)
    root.update()


def main():
    pyautogui.PAUSE=.12
    with tempfile.TemporaryDirectory(prefix='aiwack-chief-ui-') as directory:
        store=LocalStore(Path(directory)/'chief.sqlite3')
        store.setup_owner('chief_ui_owner','owner-chief-ui-password-2026')
        chief=store.add_employee_draft('chief_ui_staff','총괄 AI')
        staff=store.add_employee_draft('chief_ui_worker','실무 AI 직원')
        store.assign_reporting_line(chief,'ceo')
        mid=store.add_local_model(ModelConfig('Synthetic UI test config','llamafile',
                                             str(Path(sys.executable).resolve()),'',24))
        store.set_employee_model(chief,mid)
        store.set_employee_model(staff,mid)
        task=ops.create_task(store,'검증용 지시 업무')
        assert ops.assign_task(store,task)['employee_id']==staff
        root=tk.Tk()
        try:
            root.geometry('1080x920+20+20')
            app=AIWACKWindow(root,store)
            app.account_name.set('chief_ui_owner')
            app.account_password.set('owner-chief-ui-password-2026')
            app.submit_login()
            office=app.company_office
            office.set_view('work')
            root.update()
            draft={'task_id':task,'instruction':'SYNTHETIC OWNER-REVIEWED DRAFT ONLY',
                   'chief_model_called':False}
            reject=office.review_chief_order(draft)
            root.update()
            click(root,find_button(reject,'기각하고 닫기'))
            assert store.read_chief_task_order(task) is None
            dialog=office.review_chief_order(draft)
            root.update()
            assert dialog.winfo_viewable()
            if os.environ.get('AIWACK_CHIEF_HANDOFF_SCREENSHOT'):
                out=Path(os.environ['AIWACK_CHIEF_HANDOFF_SCREENSHOT'])
                out.parent.mkdir(parents=True,exist_ok=True)
                pyautogui.screenshot().save(out)
            click(root,find_button(dialog,'확인 후 지시 승인'))
            assert store.read_chief_task_order(task)['instruction']==draft['instruction']
            assert store.list_task_runs(task)==[]
            assert store.list_task_artifacts(task)==[]
            assert store.read_task(task)['status']=='todo'
            assert not ops.company_snapshot(store)['actual_sales_verified']
            print('REAL_MOUSE_CHIEF_ORDER_OWNER_APPROVAL_WITHOUT_EXECUTION_PASS',flush=True)
        finally:
            root.destroy()

if __name__ == '__main__':
    main()
