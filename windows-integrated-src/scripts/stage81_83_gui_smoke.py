"""Xvfb no-network owner GUI smoke for local diagnostics and draft proposals."""
from pathlib import Path
import tempfile
import tkinter as tk
import socket
from desktop.storage import LocalStore
from desktop.stage81_83_diagnostics_gui import Stage81_83OwnerWindow

def fail(*args,**kwargs):raise AssertionError('network request forbidden')

def main():
    socket.socket=fail;socket.getaddrinfo=fail;socket.create_connection=fail
    with tempfile.TemporaryDirectory() as tmp:
        store=LocalStore(Path(tmp)/'gui.sqlite3')
        store.setup_owner('mockowner','very-long-local-password')
        root=tk.Tk();root.withdraw()
        app=Stage81_83OwnerWindow(root,store)
        assert app.panel.performance()['actual_sales_data_available'] is False
        assert app.panel.diagnostics()['live_revenue_decline']=='NOT_EVALUABLE_NO_VERIFIED_SALES'
        draft=app.panel.create_draft()
        assert draft['not_an_executed_task']
        assert len(app.panel.history())==1
        app.logout()
        assert app.panel.diagnostics() is None
        assert app.panel.history() is None
        root.update_idletasks();root.destroy()
    print('PASS Stage81-83 Xvfb GUI, local owner auth, no-network socket/DNS blockers, no actual tasks or revenue, logout gate')
if __name__=='__main__':main()
