"""Exercise stage54 local batch source/version warnings in native Tkinter.

Uses only temporary SQLite/files. All socket/DNS calls are blocked.
"""
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
    raise AssertionError('Network access forbidden')


def main():
    with patch.object(socket.socket, 'connect', deny), \
         patch.object(socket.socket, 'connect_ex', deny), \
         patch.object(socket.socket, 'sendto', deny), \
         patch.object(socket.socket, 'sendall', deny), \
         patch.object(socket, 'getaddrinfo', deny):
        with tempfile.TemporaryDirectory(prefix='aiwack-bundle-version-gui-') as work:
            folder = Path(work)
            old = folder / 'existing.txt'
            old.write_text('First version saved offline', encoding='utf-8')
            new = folder / 'latest.txt'
            new.write_text('New version saved offline', encoding='utf-8')
            manifest = folder / 'bundle.json'
            manifest.write_text(json.dumps({
                'format': 'aiwack-offline-research-bundle-v1',
                'items': [{'file': 'latest.txt', 'url': 'https://sample.example/article',
                           'title': 'Latest version'}]}), encoding='utf-8')
            root = tk.Tk()
            store = LocalStore(folder / 'company.sqlite3')
            try:
                app = AIWACKWindow(root, store)
                app.account_name.set('warning-gui-owner')
                app.account_password.set('warning-gui-password-2026')
                app.password_confirm.set('warning-gui-password-2026')
                app.auth_button.invoke()
                root.update()
                existing_id = store.import_offline_research_file(
                    'https://sample.example/article', 'Older saved text', old)
                before = len(store.search_offline_research())
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno', return_value=False) as confirm:
                    app.research_bundle_button.invoke()
                    confirm.assert_called_once()
                    assert '주의: 1개 항목' in confirm.call_args.args[1]
                root.update()
                shown = app.research_detail.get('1.0', 'end')
                assert '동일 URL·다른 본문' in shown, shown
                assert str(existing_id) in shown
                assert len(store.search_offline_research()) == before
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno', return_value=True):
                    app.research_bundle_button.invoke()
                root.update()
                assert len(store.search_offline_research()) == before + 1
                assert '1건 등록' in app.research_feedback.get()
                app.sign_out()
                root.update()
            finally:
                root.destroy()
    print('PASS: Tkinter source/version warning, owner cancellation and approval, offline sockets blocked')

if __name__ == '__main__':
    main()
