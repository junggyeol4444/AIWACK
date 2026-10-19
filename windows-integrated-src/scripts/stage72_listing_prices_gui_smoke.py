"""Stage72 real Tkinter GUI smoke with sockets and DNS blocked."""
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
    with TemporaryDirectory(prefix='aiwack72-gui-') as tmp, \
         patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(Path(tmp) / 'owner.sqlite3'))
            app.account_name.set('owner72')
            app.account_password.set('stage72-long-password')
            app.password_confirm.set('stage72-long-password')
            app.auth_button.invoke(); root.update()
            assert '상품 등록·가격 초안 (미게시)' in app.quick_navigation['values']
            b = app.store.create_business(1, '사업', '목표')
            item = app.store.create_catalog_item(b, 'product', '초안', '설명', 1000, '계획')
            prototype = app.store.create_product_prototype(item)
            app.store.set_product_prototype_state(prototype, 'review_requested')
            app.store.record_product_release_review(
                prototype, {k:'unverified' for k in RELEASE_CHECKS}, '보류')
            plan = app.store.create_service_operations_plan(
                prototype, 'local_desktop_future', '담당', '백업', '롤백', '모니터')
            app.store.record_service_readiness(
                plan['id'], {k:'unverified' for k in OPS_CHECKS}, '')
            contract = app.store.create_sales_channel_contract(
                plan['id'], 'marketplace_future', '미래 채널', 'KR_future',
                'manual_future', ['listing_draft_future'], '매핑', '법무')
            app.store.review_sales_channel_contract(
                contract['id'], {k:'unverified' for k in CHANNEL_CHECKS}, '검토')
            app.listing_contract_id.set(str(contract['id']))
            app.listing_catalog_id.set(str(item))
            app.listing_title.set('미게시 상품')
            app.listing_description.set('상품 설명')
            app.listing_price_minor.set('2000')
            app.listing_price_note.set('미검증 가격 가정')
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app._listing_create(); root.update()
            assert app.store.unpublished_listings() == []
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._listing_create(); root.update()
            ident = int(app.listing_draft_id.get())
            assert app.store.unpublished_listing(ident)['state'] == 'DRAFT_UNPUBLISHED'
            app.listing_price_minor.set('2500')
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._listing_revise(); root.update()
            assert app.store.unpublished_listing(ident)['price_minor'] == 2500
            app.listing_review_note.set('관리자 검토')
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._listing_review(); root.update()
            assert app.store.unpublished_listing(ident)['state'] == 'REVIEWED_UNPUBLISHED'
            app.listing_review_note.set('계획 폐기')
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._listing_retire(); root.update()
            assert app.store.unpublished_listing(ident)['state'] == 'RETIRED_UNPUBLISHED'
            assert len(app.listing_tree.get_children()) == 1
            app.sign_out(); root.update()
            app._listing_refresh(); root.update()
            assert '거부' in app.listing_feedback.get()
        finally:
            root.destroy()
    print('PASS Stage72 GUI: create/cancel/revise/review/retire/logout, no network/publishing')


if __name__ == '__main__':
    main()
