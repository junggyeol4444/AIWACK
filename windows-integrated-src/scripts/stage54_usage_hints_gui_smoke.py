"""Exercise actual Tkinter owner preview; no web, DNS, or SQLite write on cancel."""
import json
from pathlib import Path
import socket
import tempfile
import tkinter as tk
from unittest.mock import patch
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def blocked(*args, **kwargs):
    raise AssertionError('network forbidden')


def main():
    with patch.object(socket.socket, 'connect', blocked), \
         patch.object(socket.socket, 'sendto', blocked), \
         patch.object(socket, 'getaddrinfo', blocked):
        with tempfile.TemporaryDirectory(prefix='aiwack-usage-hints-') as temp:
            folder=Path(temp)
            (folder/'source.html').write_text(
                '<h1>Local research</h1><meta name="robots" content="noindex,nofollow">'
                '<link rel="license" href="https://license.example.net/?key=SECRET">',
                encoding='utf-8')
            manifest=folder/'bundle.json'
            manifest.write_text(json.dumps({'format':'aiwack-offline-research-bundle-v1',
                'items':[{'file':'source.html','url':'https://example.org/page','title':'Research'}]}),
                encoding='utf-8')
            store=LocalStore(folder/'data.db')
            store.setup_owner('owner','local-secret')
            root=tk.Tk()
            try:
                app=AIWACKWindow(root,store)
                app.account_name.set('owner')
                app.account_password.set('local-secret')
                app.auth_button.invoke()
                root.update()
                assert store.is_authenticated
                with patch('desktop.app.filedialog.askopenfilename',return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno',return_value=False) as confirmation:
                    app.research_bundle_button.invoke()
                    confirmation.assert_called_once()
                    assert 'HTML 이용·색인 자기 표기 2건' in confirmation.call_args.args[1]
                detail=app.research_detail.get('1.0','end')
                assert 'HTML 이용/색인 자기 표기' in detail
                assert 'license.example.net' in detail
                assert 'SECRET' not in detail
                assert store.search_offline_research() == []
                with patch('desktop.app.filedialog.askopenfilename',return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno',return_value=True):
                    app.research_bundle_button.invoke()
                assert len(store.search_offline_research()) == 1
                print('PASS: usage hints preview, cancel, approve; inert offline GUI')
            finally:
                root.destroy()

if __name__ == '__main__':
    main()
