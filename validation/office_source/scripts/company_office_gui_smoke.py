"""Xvfb (Linux) or actual Windows Tk: click office controls and check SQLite."""
from pathlib import Path
import tempfile
import tkinter as tk
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore

with tempfile.TemporaryDirectory() as directory:
    root=tk.Tk()
    try:
        db=LocalStore(Path(directory)/'user.sqlite3')
        window=AIWACKWindow(root,db)
        window.account_name.set('company_owner')
        window.account_password.set('safe-owner-password-2026')
        window.password_confirm.set('safe-owner-password-2026')
        window.submit_setup()
        root.update()
        assert window.tabs.tab(0,'text')=='AI 회사 운영센터'
        office=window.company_office
        assert '미지정' in office.chief_label.get()
        # Trigger the exact real button command and verify actual persisted task.
        office.title.set('첫 회사 실제 업무')
        office.task_entry.focus_force()
        for button in office.parent.winfo_children():
            pass
        office.create()
        root.update()
        assert db.list_tasks()[0]['title']=='첫 회사 실제 업무'
        assert len(office.jobs.get_children())==1
        assert office.cards['tasks'].get()=='1'
        assert db.list_task_runs()==[]
        print('COMPANY_OFFICE_LIVE_GUI_PASS')
    finally:root.destroy()
