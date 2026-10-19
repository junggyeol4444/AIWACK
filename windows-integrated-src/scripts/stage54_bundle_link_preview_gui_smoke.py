"""Native Tk test: outbound HTML references in offline bundle approval."""
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


def forbidden(*args, **kwargs):
    raise AssertionError('Network or DNS forbidden in GUI test')


def main():
    with patch.object(socket.socket, 'connect', forbidden), \
         patch.object(socket.socket, 'connect_ex', forbidden), \
         patch.object(socket.socket, 'sendall', forbidden), \
         patch.object(socket.socket, 'sendto', forbidden), \
         patch.object(socket, 'getaddrinfo', forbidden):
        with tempfile.TemporaryDirectory(prefix='aiwack-bundle-link-') as raw:
            folder = Path(raw)
            (folder/'page.html').write_text('<h1>Archived snapshot</h1>'
                '<a href="/included">included</a>'
                '<a href="https://outside.example/unknown">unknown</a>', encoding='utf-8')
            (folder/'included.txt').write_text('second local document', encoding='utf-8')
            manifest = folder/'manifest.json'
            manifest.write_text(json.dumps({'format': 'aiwack-offline-research-bundle-v1',
                'items': [{'file': 'page.html', 'url': 'https://example.org/index', 'title': 'Page'},
                          {'file': 'included.txt', 'url': 'https://example.org/included', 'title': 'Second'}]}),
                encoding='utf-8')
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
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno', return_value=False) as confirm:
                    app.research_bundle_button.invoke()
                    confirm.assert_called_once()
                    assert 'HTML 참조 링크 1건' in confirm.call_args.args[1]
                text = app.research_detail.get('1.0', 'end')
                assert 'HTML 참조 링크(오프라인): 2건' in text, text
                assert '묶음 내 등록 후보: https://example.org/included' in text
                assert '로컬 미등록: https://outside.example/unknown' in text
                assert len(store.search_offline_research()) == 0
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno', return_value=True):
                    app.research_bundle_button.invoke()
                assert len(store.search_offline_research()) == 2
                app.sign_out()
            finally:
                root.destroy()
    print('PASS: native Tk HTML link summary, denial, explicit approval; no network')


if __name__ == '__main__':
    main()
