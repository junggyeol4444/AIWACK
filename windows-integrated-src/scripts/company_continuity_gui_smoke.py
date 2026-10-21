"""Genuine Tk button->owner-reviewed failure audit->SQLite fresh login; no fake OS kill."""
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import messagebox,simpledialog
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore
from desktop import company_autopilot as auto
from desktop import company_continuity as continuity

with tempfile.TemporaryDirectory() as folder:
    root=tk.Tk()
    saved=(messagebox.askyesno,simpledialog.askstring,simpledialog.askinteger)
    try:
        db=LocalStore(Path(folder)/'gui.sqlite3')
        gui=AIWACKWindow(root,db)
        gui.account_name.set('owner')
        gui.account_password.set('long-continuity-GUI-password-2026')
        gui.password_confirm.set('long-continuity-GUI-password-2026')
        gui.submit_setup()
        office=gui.company_office
        office.set_view('planning')
        root.update()
        auto.configure(db,True,now=100)
        with db._connect() as con:
            con.execute("INSERT INTO aiwack_autopilot_runs(planned_at,state,started_at) VALUES(100,'running',datetime('now','-300 seconds'))")
            rid=con.execute('SELECT MAX(id) FROM aiwack_autopilot_runs').fetchone()[0]
        office._autopilot_poll()
        assert continuity.observed_gui_continuity(db)['observed_heartbeat_rows']>=1
        def find(widget,title):
            for child in widget.winfo_children():
                if isinstance(child,tk.Button) and child.cget('text')==title:return child
                matched=find(child,title)
                if matched:return matched
            return None
        button=find(root,'중단된 AI 실행 수기 복구')
        assert button and button.winfo_viewable()
        assert button.winfo_rooty()+button.winfo_height()<=root.winfo_rooty()+root.winfo_height()
        messagebox.askyesno=lambda *a,**kw:True
        simpledialog.askstring=lambda title,*a,**kw:('tick' if title=='복구 분류' else '실제 Windows 프로세스 직접 확인함')
        simpledialog.askinteger=lambda *a,**kw:rid
        button.invoke()
        root.update()
        assert continuity.read_recovery_audit(db)[0]['run_id']==rid
        assert any(x['id']==rid and x['state']=='failed' for x in auto.history(db))
        db.logout()
        reopened=LocalStore(db.path)
        reopened.login('owner','long-continuity-GUI-password-2026')
        assert len(continuity.read_recovery_audit(reopened))==1
        assert continuity.observed_gui_continuity(reopened)['observed_heartbeat_rows']>=1
        print('NATIVE_TK_24H_HEARTBEAT_AND_OWNER_CRASH_RECOVERY_AUDIT_PASS')
        print('NO_REAL_WINDOWS_24H_SOAK_OR_OS_TERMINATION_ASSERTED')
    finally:
        messagebox.askyesno,simpledialog.askstring,simpledialog.askinteger=saved
        root.destroy()
