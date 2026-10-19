"""Stage71 real Tkinter smoke under Xvfb, sockets and DNS blocked."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import socket
import tkinter as tk

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore
from desktop.product_release_review import CHECKS as RELEASE_CHECKS
from desktop.service_operations_plan import CHECKS as OPS_CHECKS


def main():
    def forbidden(*args, **kwargs):
        raise AssertionError('network forbidden')
    with TemporaryDirectory(prefix='aiwack71-gui-') as tmp, \
         patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(Path(tmp) / 'owner.sqlite3'))
            app.account_name.set('owner71')
            app.account_password.set('stage71-long-password')
            app.password_confirm.set('stage71-long-password')
            app.auth_button.invoke(); root.update()
            assert '판매 채널 연결 계획 (미연결)' in app.quick_navigation['values']
            b = app.store.create_business(1, '사업', '목표')
            c = app.store.create_catalog_item(b, 'service', '초안', '설명', 1000, '계획')
            p = app.store.create_product_prototype(c)
            app.store.set_product_prototype_state(p, 'review_requested')
            app.store.record_product_release_review(p, {k: 'unverified' for k in RELEASE_CHECKS}, '보류')
            ops = app.store.create_service_operations_plan(
                p, 'local_desktop_future', '담당', '백업', '롤백', '모니터링')
            app.store.record_service_readiness(
                ops['id'], {k: 'unverified' for k in OPS_CHECKS}, '')
            app.sales_channel_ops_id.set(str(ops['id']))
            app.sales_channel_name.set('테스트 예정 채널')
            app.sales_channel_mapping.set('상품 정보 매핑 계획')
            app.sales_channel_compliance.set('규정 검토 예정')
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app._sales_channel_create(); root.update()
            assert app.store.sales_channel_contracts() == []
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._sales_channel_create(); root.update()
            ident = int(app.sales_channel_id.get())
            assert app.store.sales_channel_contract(ident)['state'] == 'DRAFT_DISCONNECTED'
            app.sales_channel_checks['owner_authorization'].set('owner_reports_prepared')
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._sales_channel_review(); root.update()
            assert app.store.sales_channel_contract(ident)['state'] == 'REVIEWED_DISCONNECTED'
            app.sales_channel_note.set('계획 중단')
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._sales_channel_retire(); root.update()
            assert app.store.sales_channel_contract(ident)['state'] == 'RETIRED_DISCONNECTED'
            assert len(app.sales_channel_tree.get_children()) == 1
            app.sign_out(); root.update()
            app._sales_channel_refresh(); root.update()
            assert '거부' in app.sales_channel_feedback.get()
        finally:
            root.destroy()
    print('PASS Stage71 GUI: create/cancel/review/retire/logout, no network or connection')


if __name__ == '__main__':
    main()
