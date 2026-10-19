"""Real Tkinter approval flow: inert base/refresh warnings without sockets."""
import json
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def deny(*_args, **_kwargs):
    raise AssertionError('network or DNS access forbidden')


def main():
    with patch.object(socket.socket, 'connect', deny), \
         patch.object(socket.socket, 'connect_ex', deny), \
         patch.object(socket.socket, 'sendall', deny), \
         patch.object(socket.socket, 'sendto', deny), \
         patch.object(socket, 'getaddrinfo', deny):
        with tempfile.TemporaryDirectory(prefix='aiwack-navigation-gui-') as directory:
            folder = Path(directory)
            (folder / 'page.html').write_text(
                '<h1>Local evidence text</h1>'
                '<base href="https://untrusted.example/assets/">'
                '<meta http-equiv="refresh" content="0;url=javascript:alert(1)">',
                encoding='utf-8')
            manifest = folder / 'manifest.json'
            manifest.write_text(json.dumps({
                'format': 'aiwack-offline-research-bundle-v1',
                'items': [{'file': 'page.html', 'url': 'https://example.org/article',
                           'title': 'Captured HTML'}]}, ensure_ascii=False), encoding='utf-8')
            store = LocalStore(folder / 'company.sqlite3')
            store.setup_owner('navigation-owner', 'offline-owner-password')
            root = tk.Tk()
            try:
                app = AIWACKWindow(root, store)
                app.account_name.set('navigation-owner')
                app.account_password.set('offline-owner-password')
                app.auth_button.invoke()
                root.update()
                assert store.is_authenticated
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno', return_value=False) as confirmation:
                    app.research_bundle_button.invoke()
                    confirmation.assert_called_once()
                    assert 'HTML 내 base/자동 이동 지시 2건' in confirmation.call_args.args[1]
                detail = app.research_detail.get('1.0', 'end')
                assert 'HTML 이동 지시(실행 안 함): 2건' in detail, detail
                assert 'https://untrusted.example/assets/' in detail
                assert '유효하지 않은 URL' in detail
                assert len(store.search_offline_research()) == 0
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno', return_value=True):
                    app.research_bundle_button.invoke()
                assert len(store.search_offline_research()) == 1
                root.update()
                print('PASS real Tkinter navigation directives, cancel/approve; network blocked')
            finally:
                root.destroy()


if __name__ == '__main__':
    main()
