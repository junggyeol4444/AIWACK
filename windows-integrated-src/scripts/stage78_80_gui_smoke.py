"""Local owner GUI smoke; socket and DNS are prohibited for this process."""
import socket
import tempfile
from pathlib import Path
import tkinter as tk
from desktop.storage import LocalStore
from desktop.stage78_80_finance_gui import Stage78_80OwnerWindow
from test_stage73_simulated_orders import prepared

def prohibited(*args,**kwargs):raise AssertionError('network operation attempted')

def main():
    socket.socket=prohibited
    socket.create_connection=prohibited
    socket.getaddrinfo=prohibited
    with tempfile.TemporaryDirectory() as tmp:
        s=LocalStore(Path(tmp)/'mock_gui.sqlite3')
        s.setup_owner('mockowner','test-password-long-enough')
        listing=prepared(s)
        order=s.create_simulated_order(listing,'stage78_gui_order',1)
        with s._connect() as con:
            bid=con.execute('SELECT c.business_id FROM local_unpublished_listings l JOIN local_catalog_items c ON c.id=l.catalog_item_id WHERE l.id=?',(listing,)).fetchone()[0]
        root=tk.Tk();root.withdraw()
        app=Stage78_80OwnerWindow(root,s)
        panel=app.panel
        panel.fields['order_id'].set(str(order['id']))
        panel.fields['business_id'].set(str(bid))
        t=panel.create_ticket()
        assert t and t['real_customer'] is False
        assert panel.transition_ticket()['state']=='REVIEW_SIMULATED'
        assert len(panel.ticket_history())==2
        money=panel.record_finance()
        assert money and money['verified_revenue'] is False
        assert len(panel.finance_history())==1
        report=panel.budget_report()
        assert report['includes_real_transactions'] is False
        snap=panel.budget_snapshot()
        assert snap and snap['report']['simulated_only']
        assert len(panel.budget_history())==1
        app.logout()
        assert panel.budget_report() is None
        assert panel.finance_history() is None
        root.update_idletasks();root.destroy()
    print('PASS Stage78-80 Linux Xvfb GUI / owner gate / offline socket DNS blockers / logout; NO customer message or financial operation')
if __name__=='__main__':main()
