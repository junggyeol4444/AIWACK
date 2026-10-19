"""Actual Tkinter guarded bundle import when local SQLite changes during approval."""
import json
import socket
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def forbid(*args, **kwargs):
    raise AssertionError('No remote network operation is permitted')


def main():
    with patch.object(socket.socket, 'connect', forbid), \
         patch.object(socket.socket, 'connect_ex', forbid), \
         patch.object(socket.socket, 'sendall', forbid), \
         patch.object(socket.socket, 'sendto', forbid), \
         patch.object(socket, 'getaddrinfo', forbid):
        with tempfile.TemporaryDirectory(prefix='aiwack-stage54-context-gui-') as temp:
            folder = Path(temp)
            (folder / 'piece.txt').write_text('Locally provided data', encoding='utf-8')
            manifest = folder / 'manifest.json'
            manifest.write_text(json.dumps({
                'format': 'aiwack-offline-research-bundle-v1',
                'items': [{'file': 'piece.txt', 'url': 'https://example.org/report',
                           'title': 'Offline item'}]}), encoding='utf-8')
            store = LocalStore(folder / 'company.sqlite3')
            root = tk.Tk()
            try:
                app = AIWACKWindow(root, store)
                app.account_name.set('context-gui-owner')
                app.account_password.set('context-gui-password-2026')
                app.password_confirm.set('context-gui-password-2026')
                app.auth_button.invoke()
                root.update()
                assert not store.search_offline_research()

                def insert_during_approval(*args, **kwargs):
                    store.add_offline_research('https://example.org/report',
                                               'Earlier source', 'Different offline local version')
                    return True

                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno', side_effect=insert_during_approval):
                    app.research_bundle_button.invoke()
                root.update()
                assert len(store.search_offline_research()) == 1
                assert '다시 검토' in app.research_feedback.get(), app.research_feedback.get()
                assert '관련 SQLite 조사 자료' in app.research_detail.get('1.0', 'end')
                # Repreview now surfaces the new conflicting record, with approval required.
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno', return_value=False):
                    app.research_bundle_button.invoke()
                root.update()
                assert '동일 URL·다른 본문' in app.research_detail.get('1.0', 'end')
                assert len(store.search_offline_research()) == 1
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno', return_value=True):
                    app.research_bundle_button.invoke()
                root.update()
                assert len(store.search_offline_research()) == 2
                assert '1건 등록' in app.research_feedback.get()
                app.sign_out()
                root.update()
            finally:
                root.destroy()
    print('PASS: GUI approval race rejected, refreshed warnings, explicit new approval offline')


if __name__ == '__main__':
    main()
