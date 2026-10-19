"""Tests no socket/DNS in Stage84-86 Linux Xvfb GUI."""
import tempfile
from pathlib import Path
import socket
import tkinter as tk
from desktop.storage import LocalStore
from desktop.stage84_86_dashboard_gui import Stage84_86OwnerWindow

def fail(*args,**kw):raise AssertionError('external network attempted')

def main():
    socket.socket=fail;socket.getaddrinfo=fail;socket.create_connection=fail
    with tempfile.TemporaryDirectory() as tmp:
        s=LocalStore(Path(tmp)/'test.sqlite3')
        s.setup_owner('owner','owner-test-password-long')
        with s._connect() as con:
            dept=con.execute("INSERT INTO company_departments(name) VALUES('Mock GUI Dept')").lastrowid
            model=con.execute("INSERT INTO ai_local_models(name,backend,executable_path,model_path,max_tokens) VALUES('Mock registered','llama_cpp','synthetic','unavailable.gguf',128)").lastrowid
        root=tk.Tk();root.withdraw()
        app=Stage84_86OwnerWindow(root,s)
        p=app.panel;p.vars['department'].set(str(dept));p.vars['model_id'].set(str(model))
        assert p.staff_draft()['agent_launched'] is False
        assert p.models()['validated_real_model_count']==0
        assert p.model_draft()['real_model_switched'] is False
        assert p.refresh()['live_monitoring'] is False
        assert len(p.histories()['staffing'])==1
        app.logout()
        assert p.refresh() is None
        root.update_idletasks();root.destroy()
    print('PASS Stage84-86 Linux Xvfb no socket/DNS, staffing and model draft, snapshot and logout; no agent or model execution')
if __name__=='__main__':main()
