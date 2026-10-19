"""Linux Xvfb smoke for non-network GUI and local stop. Never runs a real agent."""
import socket
import tempfile
from pathlib import Path
import tkinter as tk
from desktop.storage import LocalStore
from desktop.stage87_90_management_gui import Stage87_90Window

def deny(*a,**k):raise AssertionError('unexpected outbound network')

def main():
    socket.socket=deny
    socket.create_connection=deny
    socket.getaddrinfo=deny
    with tempfile.TemporaryDirectory() as d:
        store=LocalStore(Path(d)/'owner.sqlite3')
        store.setup_owner('owner','some-long-password-123')
        root=tk.Tk();root.withdraw()
        gui=Stage87_90Window(root,store)
        p=gui.panel
        assert p.view('organization')['read_only']
        assert p.view('communications')['live_ai_chat'] is False
        assert p.view('commerce')['actual_sales_verified'] is False
        assert p.change_stop(True)['stopped'] is True
        assert p.view('approvals')['local_emergency_stopped']
        assert p.change_stop(False)['stopped'] is False
        gui.logout()
        assert p.view('organization') is None
        root.update_idletasks();root.destroy()
    print('PASS Stage87-90 local owner GUI under blocked socket/DNS; no real external actions')
if __name__=='__main__':main()
