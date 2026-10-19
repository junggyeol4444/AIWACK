"""Real Tk window + mouse-click smoke for local model connection screen.

This is source-window GUI testing, not packaged EXE or GGUF inference.
"""
from __future__ import annotations
import json
import os
import tempfile
import tkinter as tk
from pathlib import Path
import pyautogui

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def recursively_find(widget, label):
    for child in widget.winfo_children():
        if isinstance(child, tk.Button) and child.cget('text') == label:
            return child
        found=recursively_find(child,label)
        if found is not None:
            return found
    return None


def screen_click(widget):
    assert widget.winfo_viewable(), 'widget must be on actual screen'
    x=widget.winfo_rootx()+widget.winfo_width()//2
    y=widget.winfo_rooty()+widget.winfo_height()//2
    pyautogui.click(x,y)


def main():
    pyautogui.PAUSE=.12
    with tempfile.TemporaryDirectory(prefix='aiwack-model-ui-') as directory:
        store=LocalStore(Path(directory)/'office.sqlite3')
        store.setup_owner('test_owner','test-owner-long-password-2026')
        employee=store.add_employee_draft('local_worker','검증용 AI 직원')
        root=tk.Tk()
        try:
            root.geometry('1100x900+20+20')
            app=AIWACKWindow(root,store)
            app.account_name.set("test_owner")
            app.account_password.set("test-owner-long-password-2026")
            app.submit_login()
            office=app.company_office
            office.set_view('organization')
            root.update()
            button=recursively_find(office.parent,'로컬 모델 연결')
            assert button is not None
            screen_click(button)
            root.update()
            dialogs=[office.model_dialog.window]
            assert dialogs[0].title()=='AIWACK | 로컬 AI 모델 연결'
            assert len(dialogs)==1, 'GUI click must open actual local model wizard'
            dialog=dialogs[0]
            assert dialog.winfo_viewable()
            assert office.store.read_employee_model(employee) is None
            if os.environ.get('AIWACK_MODEL_WIZARD_SCREENSHOT'):
                out=Path(os.environ['AIWACK_MODEL_WIZARD_SCREENSHOT'])
                out.parent.mkdir(parents=True,exist_ok=True)
                pyautogui.screenshot().save(out)
            print('REAL_MOUSE_OPENED_LOCAL_MODEL_WIZARD', json.dumps({
                'employee': employee,'actual_model_calls':len(store.list_employee_model_calls())}))
            app.sign_out()
            root.update()
            assert not dialog.winfo_exists(), 'Model path dialog must close on logout'
            assert app.main_frame is None
            print('LOGOUT_CLOSED_SENSITIVE_MODEL_WIZARD')
        finally:
            root.destroy()

if __name__=='__main__':
    main()
