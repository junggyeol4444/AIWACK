"""Stage70 actual Tkinter panel with all socket and DNS calls forbidden."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import socket
import tkinter as tk

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore
from desktop.product_release_review import CHECKS as RELEASE_CHECKS


def main():
    def forbidden(*args, **kwargs):
        raise AssertionError('network forbidden')
    with TemporaryDirectory(prefix='aiwack70-gui-') as tmp, \
         patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(Path(tmp) / 'owner.sqlite3'))
            app.account_name.set('owner70')
            app.account_password.set('stage70-long-password')
            app.password_confirm.set('stage70-long-password')
            app.auth_button.invoke(); root.update()
            assert '서비스 배포·운영 계획 (미배포)' in app.quick_navigation['values']
            b = app.store.create_business(1, '사업', '목표')
            c = app.store.create_catalog_item(b, 'service', '초안', '설명', 1000, '계획')
            p = app.store.create_product_prototype(c)
            app.store.set_product_prototype_state(p, 'review_requested')
            app.store.record_product_release_review(p, {k: 'unverified' for k in RELEASE_CHECKS}, '보류')
            app.service_ops_prototype_id.set(str(p))
            app.service_ops_operator.set('관리자 검토')
            app.service_ops_backup.set('백업 계획')
            app.service_ops_rollback.set('복구 계획')
            app.service_ops_monitor.set('상태 검사 계획')
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app._service_ops_create(); root.update()
            assert app.store.service_operations_plans() == []
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._service_ops_create(); root.update()
            ident = int(app.service_ops_plan_id.get())
            app.service_ops_checks['operator_assigned'].set('owner_reports_prepared')
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._service_ops_record(); root.update()
            assert app.store.service_operations_plan(ident)['state'] == 'REVIEWED_NO_DEPLOY'
            app.service_ops_note.set('폐기')
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._service_ops_retire(); root.update()
            assert app.store.service_operations_plan(ident)['state'] == 'RETIRED_NO_DEPLOY'
            assert len(app.service_ops_tree.get_children()) == 1
            app.sign_out(); root.update()
            app._service_ops_refresh(); root.update()
            assert '거부' in app.service_ops_feedback.get()
        finally:
            root.destroy()
    print('PASS Stage70 GUI: cancel/create/owner claims/retire/logout; no network or deployment')


if __name__ == '__main__':
    main()
