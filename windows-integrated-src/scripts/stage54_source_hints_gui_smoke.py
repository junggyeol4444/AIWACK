"""Actual offline Tkinter approval dialogue for inert HTML source hints."""
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


def deny(*args, **kwargs):
    raise AssertionError('Outbound socket/DNS forbidden')


def main():
    with patch.object(socket.socket, 'connect', deny), \
         patch.object(socket.socket, 'connect_ex', deny), \
         patch.object(socket.socket, 'sendall', deny), \
         patch.object(socket.socket, 'sendto', deny), \
         patch.object(socket, 'getaddrinfo', deny):
        with tempfile.TemporaryDirectory(prefix='aiwack-hints-gui-') as directory:
            folder = Path(directory)
            (folder/'article.html').write_text('<h1>Offline capture</h1>'
                '<link rel="canonical" href="https://different.example/article">'
                '<meta property="og:url" content="https://example.org/article">', encoding='utf-8')
            bundle = folder/'bundle.json'
            bundle.write_text(json.dumps({'format': 'aiwack-offline-research-bundle-v1',
                'items': [{'file': 'article.html', 'url': 'https://example.org/article',
                           'title': 'Source hints'}]}), encoding='utf-8')
            store = LocalStore(folder/'company.sqlite3')
            store.setup_owner('hint-owner', 'offline-test-owner-password')
            root = tk.Tk()
            try:
                app = AIWACKWindow(root, store)
                app.account_name.set('hint-owner')
                app.account_password.set('offline-test-owner-password')
                app.auth_button.invoke()
                root.update()
                assert store.is_authenticated
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(bundle)), \
                     patch('desktop.app.messagebox.askyesno', return_value=False) as confirmation:
                    app.research_bundle_button.invoke()
                    confirmation.assert_called_once()
                    assert 'HTML 내부 출처 자체 표기 1건' in confirmation.call_args.args[1]
                detail = app.research_detail.get('1.0', 'end')
                assert 'HTML 자기 출처 표기(미검증): 2건' in detail, detail
                assert 'https://different.example/article' in detail
                assert len(store.search_offline_research()) == 0
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(bundle)), \
                     patch('desktop.app.messagebox.askyesno', return_value=True):
                    app.research_bundle_button.invoke()
                assert len(store.search_offline_research()) == 1
                root.update()
                print('PASS Tkinter source hints preview, cancel, explicit approval; sockets blocked')
            finally:
                root.destroy()


if __name__ == '__main__':
    main()
