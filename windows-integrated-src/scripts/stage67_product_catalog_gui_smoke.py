"""Linux Xvfb Tkinter Stage67 offline product/service planning smoke test."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import socket
import tkinter as tk

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    def forbidden(*args, **kwargs): raise AssertionError('network forbidden')
    with TemporaryDirectory(prefix='aiwack67-gui-') as tmp, \
         patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(Path(tmp) / 'owner.sqlite3'))
            app.account_name.set('owner67')
            app.account_password.set('stage67-long-password')
            app.password_confirm.set('stage67-long-password')
            app.auth_button.invoke(); root.update()
            assert '상품·서비스 정보 관리' in app.quick_navigation['values']
            b = app.store.create_business(1, '사업 A', '목표')
            project = app.store.create_business_project(b, '프로젝트', '목표')
            app.catalog_business_id.set(str(b))
            app.catalog_project_id.set(str(project))
            app.catalog_name.set('오프라인 상품')
            app.catalog_description.set('가정한 설명')
            app.catalog_delivery.set('제공 계획')
            app.catalog_price.set('5000')
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app._catalog_create(); root.update()
            assert app.store.catalog_items() == []
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._catalog_create(); root.update()
            p = app.store.catalog_items()[0]['id']
            assert app.store.catalog_item(p)['project_id'] == project
            app.catalog_price.set('6000')
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._catalog_revise(); root.update()
            assert app.store.catalog_item(p)['assumed_price_krw'] == 6000
            app.catalog_state.set('review_pending')
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._catalog_change_state(); root.update()
            assert app.store.catalog_item(p)['state'] == 'review_pending'
            app.sign_out(); root.update()
            app._catalog_refresh(); root.update()
            assert '거부' in app.catalog_feedback.get()
        finally:
            root.destroy()
    print('PASS Stage67 Tk: owner, cancel, project link, revision, review, logout; sockets/DNS blocked')


if __name__ == '__main__':
    main()
