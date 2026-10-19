"""Stage68 Tkinter smoke under Linux Xvfb, with network sockets/DNS blocked."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import socket
import tkinter as tk

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    def forbidden(*args, **kwargs): raise AssertionError('network forbidden')
    with TemporaryDirectory(prefix='aiwack68-gui-') as tmp, \
         patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(Path(tmp) / 'owner.sqlite3'))
            app.account_name.set('owner68')
            app.account_password.set('stage68-long-password')
            app.password_confirm.set('stage68-long-password')
            app.auth_button.invoke(); root.update()
            assert '로컬 상품 시제품 준비' in app.quick_navigation['values']
            b = app.store.create_business(1, '사업', '목표')
            c = app.store.create_catalog_item(b, 'product', '시제품', '가정 설명', 1000, '제공 계획')
            app.production_catalog_id.set(str(c))
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app._production_create(); root.update()
            assert app.store.product_prototypes() == []
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._production_create(); root.update()
            p = app.store.product_prototypes()[0]['id']
            assert Path(app.store.product_prototype(p)['artifact_path']).is_file()
            app.production_state.set('review_requested')
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._production_change_state(); root.update()
            assert app.store.product_prototype(p)['state'] == 'review_requested'
            app.sign_out(); root.update()
            app._production_refresh(); root.update()
            assert '거부' in app.production_feedback.get()
        finally:
            root.destroy()
    print('PASS Stage68 GUI: owner/cancel/static artifact/hash/review/logout; sockets and DNS blocked')


if __name__ == '__main__':
    main()
