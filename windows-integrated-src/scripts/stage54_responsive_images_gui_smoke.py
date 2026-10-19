"""Live Tkinter login, preview, cancel and approval under Python network guard."""
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
    raise AssertionError('network and DNS are forbidden')


def main():
    with patch.object(socket.socket,'connect',deny), patch.object(socket.socket,'connect_ex',deny), \
         patch.object(socket.socket,'sendall',deny),patch.object(socket.socket,'sendto',deny), \
         patch.object(socket,'getaddrinfo',deny):
        with tempfile.TemporaryDirectory(prefix='aiwack-srcset-') as work:
            folder=Path(work)
            (folder/'source.html').write_text('<h1>Offline HTML</h1>'
                '<img srcset="/small.png 1x, https://cdn.example.net/large.png?session=SENSITIVE 2x">',
                encoding='utf-8')
            manifest=folder/'manifest.json'
            manifest.write_text(json.dumps({'format':'aiwack-offline-research-bundle-v1',
                'items':[{'file':'source.html','url':'https://example.org/page','title':'Claimed source'}]}),
                encoding='utf-8')
            store=LocalStore(folder/'store.db')
            store.setup_owner('owner','local-password')
            root=tk.Tk()
            try:
                app=AIWACKWindow(root,store)
                app.account_name.set('owner')
                app.account_password.set('local-password')
                app.auth_button.invoke()
                root.update()
                assert store.is_authenticated
                with patch('desktop.app.filedialog.askopenfilename',return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno',return_value=False) as yesno:
                    app.research_bundle_button.invoke()
                    yesno.assert_called_once()
                    assert '반응형 이미지 srcset 2건' in yesno.call_args.args[1]
                detail=app.research_detail.get('1.0','end')
                assert 'HTML 반응형 이미지 srcset(요청 안 함): 2건' in detail, detail
                assert 'cdn.example.net' in detail
                assert 'SENSITIVE' not in detail
                assert store.search_offline_research() == []
                with patch('desktop.app.filedialog.askopenfilename',return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno',return_value=True):
                    app.research_bundle_button.invoke()
                assert len(store.search_offline_research()) == 1
                print('PASS Tkinter responsive image preview, cancel, approve; no network')
            finally:
                root.destroy()

if __name__ == '__main__':
    main()
