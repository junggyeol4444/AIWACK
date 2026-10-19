"""Real Tkinter form/iframe/script target preview without network access."""
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
    raise AssertionError('network/DNS forbidden')


def main():
    with patch.object(socket.socket, 'connect', deny), \
         patch.object(socket.socket, 'connect_ex', deny), \
         patch.object(socket.socket, 'sendall', deny), \
         patch.object(socket.socket, 'sendto', deny), \
         patch.object(socket, 'getaddrinfo', deny):
        with tempfile.TemporaryDirectory(prefix='aiwack-active-targets-') as directory:
            folder=Path(directory)
            (folder/'evidence.html').write_text(
                '<h1>Local captured HTML</h1>'
                '<form method="POST" action="https://other.example/submit"></form>'
                '<iframe src="/embed"></iframe>'
                '<script src="data:text/plain,bad"></script>',encoding='utf-8')
            manifest=folder/'manifest.json'
            manifest.write_text(json.dumps({'format':'aiwack-offline-research-bundle-v1',
                 'items':[{'file':'evidence.html','url':'https://example.org/report',
                           'title':'Local HTML'}]}),encoding='utf-8')
            store=LocalStore(folder/'company.sqlite3')
            store.setup_owner('active-owner','local-only-password')
            root=tk.Tk()
            try:
                app=AIWACKWindow(root,store)
                app.account_name.set('active-owner')
                app.account_password.set('local-only-password')
                app.auth_button.invoke()
                root.update()
                assert store.is_authenticated
                with patch('desktop.app.filedialog.askopenfilename',return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno',return_value=False) as confirm:
                    app.research_bundle_button.invoke()
                    confirm.assert_called_once()
                    assert 'HTML 폼·iframe·외부 script 대상 3건' in confirm.call_args.args[1]
                detail=app.research_detail.get('1.0','end')
                assert 'HTML 폼·삽입·스크립트 대상(실행 안 함): 3건' in detail,detail
                assert 'form POST' in detail and 'https://other.example/submit' in detail
                assert '잘못된 URL' in detail
                assert not store.search_offline_research()
                with patch('desktop.app.filedialog.askopenfilename',return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno',return_value=True):
                    app.research_bundle_button.invoke()
                assert len(store.search_offline_research()) == 1
                root.update()
                print('PASS active HTML endpoints passive preview cancel/approve, no network')
            finally:
                root.destroy()


if __name__ == '__main__':
    main()
