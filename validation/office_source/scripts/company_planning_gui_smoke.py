"""Physical mouse and keyboard checks for the actual owner planning screen."""
import os
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import messagebox
import pyautogui
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore

pyautogui.PAUSE=0.12
pyautogui.FAILSAFE=True

def find_button(widget, label):
    for child in widget.winfo_children():
        if isinstance(child,tk.Button) and child.cget('text')==label:
            return child
        found=find_button(child,label)
        if found is not None:
            return found
    return None


def real_click(root,widget):
    root.update()
    assert widget is not None and widget.winfo_viewable(), 'real button not visible'
    root.lift();root.focus_force();root.update()
    x=widget.winfo_rootx()+widget.winfo_width()//2
    y=widget.winfo_rooty()+widget.winfo_height()//2
    pyautogui.click(x,y)
    root.update()


with tempfile.TemporaryDirectory(prefix='aiwack-planning-gui-') as location:
    root=tk.Tk()
    root.geometry('1040x720+10+10')
    try:
        store=LocalStore(Path(location)/'ui.sqlite3')
        app=AIWACKWindow(root,store)
        app.account_name.set('owner_cockpit')
        app.account_password.set('safe-planning-password-2026')
        app.password_confirm.set('safe-planning-password-2026')
        app.submit_setup()
        root.update()
        office=app.company_office
        assert 'planning' in office.views
        real_click(root,office.nav_buttons['planning'])
        real_click(root,office.goal_entry)
        pyautogui.write('Synthetic research planning only',interval=.01)
        root.update()
        assert office.goal_title.get()=='Synthetic research planning only'
        real_click(root,find_button(office.views['planning'],'목표 등록·활성화'))
        assert store.list_goals()[0]['status']=='active'
        assert office.view_name=='planning'
        assert office.views['planning'].winfo_viewable()
        assert len(office.proposal_list.get_children())==0
        scan=find_button(office.views['planning'],'목표·차단 업무 검색')
        real_click(root,scan)
        assert len(office.proposal_list.get_children())==1
        if os.environ.get('AIWACK_PROPOSAL_SCREENSHOT'):
            pyautogui.screenshot().save(os.environ['AIWACK_PROPOSAL_SCREENSHOT'])
        assert store.list_tasks()==[]
        assert 'AI 호출 없음' in office.status.get()
        proposal=store.list_autonomous_task_proposals()[0]
        assert proposal['origin']=='rule'
        item=office.proposal_list.get_children()[0]
        office.proposal_list.selection_set(item)
        office.proposal_list.see(item)
        root.update()
        original=messagebox.askyesno
        messagebox.askyesno=lambda *args,**kwargs:True
        try:
            real_click(root,find_button(office.views['planning'],'업무로 승인'))
        finally:
            messagebox.askyesno=original
        assert len(store.list_tasks())==1
        assert office.view_name=='work'
        assert office.cards['tasks'].get()=='1'
        assert store.list_task_runs()==[]
        assert len(office.work_jobs.get_children())==1
        if os.environ.get('AIWACK_PLANNING_SCREENSHOT'):
            pyautogui.screenshot().save(os.environ['AIWACK_PLANNING_SCREENSHOT'])
        print('PHYSICAL_COMPANY_PLANNING_GUI_PASS: scan, select, owner approve, real task, no model call')
    finally:
        root.destroy()
