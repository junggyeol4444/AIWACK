"""Stage69 actual Tkinter GUI smoke with socket/DNS disabled."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import socket
import tkinter as tk

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    def forbidden(*args, **kwargs):
        raise AssertionError('network forbidden')
    with TemporaryDirectory(prefix='aiwack69-gui-') as tmp, \
         patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(Path(tmp) / 'owner.sqlite3'))
            app.account_name.set('owner69')
            app.account_password.set('stage69-long-password')
            app.password_confirm.set('stage69-long-password')
            app.auth_button.invoke(); root.update()
            assert '상품 검수·출시 보류 기록' in app.quick_navigation['values']
            b = app.store.create_business(1, '사업', '목표')
            c = app.store.create_catalog_item(b, 'product', '초안', '설명', 1000, '제공 계획')
            p = app.store.create_product_prototype(c)
            app.store.set_product_prototype_state(p, 'review_requested')
            app.release_review_id.set(str(p))
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app._release_review_record(); root.update()
            assert app.store.product_release_review_history(p) == []
            app.release_review_checks['description_matches_intent'].set('owner_reports_checked')
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app._release_review_record(); root.update()
            result = app.store.product_release_review_summary(p)
            assert result['review_count'] == 1 and not result['release_approved']
            assert len(app.release_review_tree.get_children()) == 1
            app.sign_out(); root.update()
            app._release_review_refresh(); root.update()
            assert '거부' in app.release_review_feedback.get()
        finally:
            root.destroy()
    print('PASS Stage69 GUI: owner/cancel/append-only review/hold/logout; sockets and DNS blocked')


if __name__ == '__main__':
    main()
