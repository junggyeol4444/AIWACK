"""Stage54 passive URL risk warnings before SQLite batch approval, real Tk GUI."""
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def forbidden(*_args, **_kwargs):
    raise AssertionError('Remote network or DNS forbidden')


def main():
    with patch.object(socket.socket, 'connect', forbidden), \
         patch.object(socket.socket, 'connect_ex', forbidden), \
         patch.object(socket.socket, 'sendall', forbidden), \
         patch.object(socket.socket, 'sendto', forbidden), \
         patch.object(socket, 'getaddrinfo', forbidden):
        with tempfile.TemporaryDirectory(prefix='aiwack54-url-review-') as path:
            folder = Path(path)
            (folder/'review.txt').write_text('Manually recorded offline text', encoding='utf-8')
            manifest = folder/'sources.json'
            store = LocalStore(folder/'company.sqlite3')
            store.setup_owner('owner', 'password-123456789')
            store.logout()
            root = tk.Tk()
            try:
                app = AIWACKWindow(root, store)
                app.account_name.set('owner')
                app.account_password.set('password-123456789')
                app.auth_button.invoke()
                root.update()
                assert store.is_authenticated
                store.create_offline_research_bundle_manifest(
                    [(folder/'review.txt', 'https://10.0.0.1/private', 'Unverified')], manifest)
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno', return_value=False) as confirm:
                    app.research_bundle_button.invoke()
                    confirm.assert_called_once()
                    assert 'URL 위험 신호: 1개 항목' in confirm.call_args.args[1]
                root.update()
                detail = app.research_detail.get('1.0', 'end')
                assert 'URL 문자열 위험 신호: 1개 항목' in detail, detail
                assert '전역 라우팅 불가 IP' in detail
                assert len(store.search_offline_research()) == 0
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno', return_value=True):
                    app.research_bundle_button.invoke()
                root.update()
                assert len(store.search_offline_research()) == 1
                assert '1건 등록' in app.research_feedback.get()
                app.sign_out()
            finally:
                root.destroy()
    print('PASS: Tkinter URL pre-approval warnings, cancellation, explicit import, offline')


if __name__ == '__main__':
    main()
