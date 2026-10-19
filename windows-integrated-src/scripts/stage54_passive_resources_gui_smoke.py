"""Actual Tkinter UI smoke for strictly offline passive media host preview."""
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
    raise AssertionError('network/DNS forbidden')


def main():
    with patch.object(socket.socket, 'connect', deny), \
         patch.object(socket.socket, 'connect_ex', deny), \
         patch.object(socket.socket, 'sendall', deny), \
         patch.object(socket.socket, 'sendto', deny), \
         patch.object(socket, 'getaddrinfo', deny):
        with tempfile.TemporaryDirectory(prefix='aiwack-passive-host-') as work:
            folder=Path(work)
            (folder/'sample.html').write_text(
                '<h1>Offline capture</h1><img src="https://tracker.example/one?token=HIDDEN-SAMPLE">'
                '<link rel="stylesheet" href="https://example.org/style.css">'
                '<video poster="file:///private/poster"></video>',encoding='utf-8')
            manifest=folder/'manifest.json'
            manifest.write_text(json.dumps({'format':'aiwack-offline-research-bundle-v1',
                'items':[{'file':'sample.html','url':'https://example.org/page',
                          'title':'Owner supplied'}]}),encoding='utf-8')
            store=LocalStore(folder/'store.db')
            store.setup_owner('owner','offline-password')
            root=tk.Tk()
            try:
                app=AIWACKWindow(root,store)
                app.account_name.set('owner')
                app.account_password.set('offline-password')
                app.auth_button.invoke()
                root.update()
                assert store.is_authenticated
                with patch('desktop.app.filedialog.askopenfilename',return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno',return_value=False) as confirm:
                    app.research_bundle_button.invoke()
                    confirm.assert_called_once()
                    assert 'HTML 이미지/스타일/미디어 참조 3건' in confirm.call_args.args[1]
                detail=app.research_detail.get('1.0','end')
                assert 'HTML 수동 리소스 참조(접속 안 함): 3건' in detail,detail
                assert 'tracker.example' in detail,detail
                assert 'HIDDEN-SAMPLE' not in detail,detail
                assert store.search_offline_research() == []
                with patch('desktop.app.filedialog.askopenfilename',return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno',return_value=True):
                    app.research_bundle_button.invoke()
                assert len(store.search_offline_research()) == 1
                root.update()
                print('PASS Tkinter passive resource review, cancellation, owner approval; no network')
            finally:
                root.destroy()

if __name__=='__main__':
    main()
