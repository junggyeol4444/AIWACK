"""Use native Tkinter to verify offline HTML form type warnings and approval."""
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
        with tempfile.TemporaryDirectory(prefix='aiwack-form-controls-') as directory:
            folder=Path(directory)
            (folder/'evidence.html').write_text(
                '<h1>Saved offline page</h1>'
                '<form method="GET" action="https://outside.example/login">'
                '<input type="password" name="password" value="DO-NOT-LEAK">'
                '<input type="file" name="upload"><input type="hidden" value="PRIVATE"></form>',
                encoding='utf-8')
            manifest=folder/'manifest.json'
            manifest.write_text(json.dumps({'format':'aiwack-offline-research-bundle-v1',
                'items':[{'file':'evidence.html', 'url':'https://example.org/report',
                          'title':'Saved HTML'}]}),encoding='utf-8')
            store=LocalStore(folder/'company.sqlite3')
            store.setup_owner('form-owner','local-only-password')
            root=tk.Tk()
            try:
                app=AIWACKWindow(root,store)
                app.account_name.set('form-owner')
                app.account_password.set('local-only-password')
                app.auth_button.invoke()
                root.update()
                assert store.is_authenticated
                with patch('desktop.app.filedialog.askopenfilename',return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno',return_value=False) as confirm:
                    app.research_bundle_button.invoke()
                    confirm.assert_called_once()
                    prompt=confirm.call_args.args[1]
                    assert 'GET 암호 입력 1건' in prompt, prompt
                    assert 'DO-NOT-LEAK' not in prompt and 'PRIVATE' not in prompt
                detail=app.research_detail.get('1.0','end')
                assert 'HTML 폼의 입력 유형(값 수집 안 함): 3건' in detail, detail
                assert 'GET 방식 암호 입력' in detail, detail
                assert 'DO-NOT-LEAK' not in detail and 'PRIVATE' not in detail
                assert store.search_offline_research() == []
                with patch('desktop.app.filedialog.askopenfilename',return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno',return_value=True):
                    app.research_bundle_button.invoke()
                assert len(store.search_offline_research()) == 1
                root.update()
                print('PASS passive HTML form-type review; cancel and explicit approve; no socket/DNS')
            finally:
                root.destroy()


if __name__ == '__main__':
    main()
