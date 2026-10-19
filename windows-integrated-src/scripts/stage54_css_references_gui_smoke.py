"""Exercise real Tkinter HTML CSS warnings with all Python network entrypoints blocked."""
import json
from pathlib import Path
import socket
import tempfile
import tkinter as tk
from unittest.mock import patch

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def deny(*args, **kwargs):
    raise AssertionError('network access forbidden')


def main():
    with patch.object(socket.socket, 'connect', deny), patch.object(socket.socket,'sendto',deny), \
         patch.object(socket,'getaddrinfo',deny):
        with tempfile.TemporaryDirectory(prefix='aiwack-css-preview-') as folder:
            tmp = Path(folder)
            (tmp/'source.html').write_text(
                '<h1>Local evidence</h1><style>@import "https://fonts.example.net/a.css?token=SECRET";'
                'body{background:url(https://images.example.net/image.png?private=HIDDEN)}</style>',
                encoding='utf-8')
            manifest = tmp/'bundle.json'
            manifest.write_text(json.dumps({'format':'aiwack-offline-research-bundle-v1',
                'items':[{'file':'source.html','url':'https://site.example.org/article','title':'Local HTML'}]}),
                encoding='utf-8')
            store=LocalStore(tmp/'data.sqlite'); store.setup_owner('owner','local-secret')
            root=tk.Tk()
            try:
                app=AIWACKWindow(root,store)
                app.account_name.set('owner'); app.account_password.set('local-secret')
                app.auth_button.invoke(); root.update(); assert store.is_authenticated
                with patch('desktop.app.filedialog.askopenfilename',return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno',return_value=False) as question:
                    app.research_bundle_button.invoke()
                    question.assert_called_once()
                    assert 'HTML 내부 CSS 참조 2건' in question.call_args.args[1]
                output=app.research_detail.get('1.0','end')
                assert 'HTML 내부 CSS 참조' in output
                assert 'fonts.example.net' in output and 'images.example.net' in output
                assert 'SECRET' not in output and 'HIDDEN' not in output
                assert not store.search_offline_research()
                with patch('desktop.app.filedialog.askopenfilename',return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno',return_value=True):
                    app.research_bundle_button.invoke()
                assert len(store.search_offline_research()) == 1
                print('PASS CSS host-only preview, owner cancel and approval, no network')
            finally:
                root.destroy()

if __name__=='__main__':
    main()
