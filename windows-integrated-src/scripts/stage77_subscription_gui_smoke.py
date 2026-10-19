"""Local Xvfb GUI smoke, requires DISPLAY. Creates only temporary mock records."""
import tempfile
from pathlib import Path
import tkinter as tk
from desktop.storage import LocalStore
from desktop.stage77_subscription_gui import Stage77OwnerWindow
from desktop.offline_subscription_refund import MODES
from test_stage73_simulated_orders import prepared


def main():
    with tempfile.TemporaryDirectory() as tmp:
        store=LocalStore(Path(tmp)/'stage77.sqlite3')
        store.setup_owner('owner77','a-super-long-test-password')
        listing=prepared(store)
        order=store.create_simulated_order(listing,'stage77_gui_order',1)
        root=tk.Tk()
        root.withdraw()
        app=Stage77OwnerWindow(root,store)
        panel=app.panel
        panel.dialogs=False
        panel.order_id.set(str(order['id']))
        panel.plan_key.set('stage77_plan_key')
        panel.mode.set(MODES[0])
        panel.periods.set('2')
        sub=panel.create_plan()
        assert sub and not sub['real_subscription']
        panel.event_key.set('stage77_cancel_key')
        panel.action.set('cancel_requested')
        assert panel.transition()['state']=='CANCEL_REQUESTED_SIMULATED'
        panel.event_key.set('stage77_refund_key')
        panel.action.set('refund_requested')
        panel.assumed_amount.set(str(order['total_minor']))
        assert panel.transition()['state']=='REFUND_REQUESTED_SIMULATED'
        assert not panel.transition()['refund_issued']
        assert len(panel.refresh())==3
        app.logout()
        assert panel.refresh() is None
        root.update_idletasks()
        root.destroy()
    print('PASS Stage77 Linux Xvfb GUI owner gate / simulated requests / logout; NO financial operation')


if __name__=='__main__':
    main()
