"""Stage73 real Tkinter GUI smoke; all sockets/DNS forbidden."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import socket
import tkinter as tk

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore
from desktop.product_release_review import CHECKS as RELEASE_CHECKS
from desktop.service_operations_plan import CHECKS as OPS_CHECKS
from desktop.sales_channel_contracts import CHECKS as CHANNEL_CHECKS


def main():
    def forbidden(*args, **kwargs):
        raise AssertionError('network forbidden')
    with TemporaryDirectory(prefix='aiwack73-gui-') as tmp, \
         patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(Path(tmp) / 'owner.sqlite3'))
            app.account_name.set('owner73')
            app.account_password.set('stage73-long-password')
            app.password_confirm.set('stage73-long-password')
            app.auth_button.invoke(); root.update()
            assert '주문 접수·상태 모의실험 (비실거래)' in app.quick_navigation['values']
            b = app.store.create_business(1, '사업', '목표')
            item = app.store.create_catalog_item(b, 'product', '상품', '설명', 1000, '계획')
            prototype = app.store.create_product_prototype(item)
            app.store.set_product_prototype_state(prototype, 'review_requested')
            app.store.record_product_release_review(
                prototype, {k:'unverified' for k in RELEASE_CHECKS}, '보류')
            plan = app.store.create_service_operations_plan(
                prototype, 'local_desktop_future', '담당', '백업', '롤백', '모니터')
            app.store.record_service_readiness(plan['id'], {k:'unverified' for k in OPS_CHECKS}, '')
            contract = app.store.create_sales_channel_contract(
                plan['id'], 'marketplace_future', '미래 채널', 'KR_future',
                'manual_future', ['listing_draft_future'], '매핑', '법무')
            app.store.review_sales_channel_contract(
                contract['id'], {k:'unverified' for k in CHANNEL_CHECKS}, '검토')
            listing = app.store.create_unpublished_listing(contract['id'], item,
                '미게시 상품', '설명', 'KRW', 2000, '미검증 가정')
            app.store.review_unpublished_listing(listing['id'], '관리자 검토')
            app.sim_listing_id.set(str(listing['id']))
            app.sim_token.set('local_gui_0001')
            app.sim_quantity.set('3')
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app._sim_order_create(); root.update()
            assert app.store.simulated_orders() == []
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._sim_order_create(); root.update()
            ident = int(app.sim_order_id.get())
            assert app.store.simulated_order(ident)['total_minor'] == 6000
            app.sim_note.set('관리자 모의 검토')
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._sim_order_transition('owner_reviewed'); root.update()
            assert app.store.simulated_order(ident)['state'] == 'REVIEWED_SIMULATED'
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._sim_order_transition('closed'); root.update()
            assert app.store.simulated_order(ident)['state'] == 'CLOSED_SIMULATED'
            assert not app.store.simulated_order(ident)['payment_received']
            assert len(app.sim_order_tree.get_children()) == 1
            app.sign_out(); root.update()
            app._sim_order_refresh(); root.update()
            assert '거부' in app.sim_feedback.get()
        finally:
            root.destroy()
    print('PASS Stage73 GUI: local simulation/cancel/review/close/logout, no network, no real commerce')


if __name__ == '__main__':
    main()
