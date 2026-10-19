"""Native Tkinter stage54 preview: cancel, modified file, success, no sockets."""
from pathlib import Path
import json
import socket
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def denied(*args, **kwargs):
    raise AssertionError('network access forbidden')


def main():
    with patch.object(socket.socket, 'connect', denied), \
         patch.object(socket.socket, 'connect_ex', denied), \
         patch.object(socket.socket, 'sendto', denied), \
         patch.object(socket.socket, 'sendall', denied), \
         patch.object(socket, 'getaddrinfo', denied):
        with tempfile.TemporaryDirectory(prefix='aiwack54-preview-') as directory:
            base = Path(directory)
            contents = base / 'entry.txt'
            contents.write_text('Locally saved offline text', encoding='utf-8')
            manifest = base / 'batch.json'
            manifest.write_text(json.dumps({
                'format': 'aiwack-offline-research-bundle-v1',
                'items': [{'file': 'entry.txt', 'url': 'https://example.org/preview',
                           'title': 'Sample'}]}), encoding='utf-8')
            root = tk.Tk()
            store = LocalStore(base / 'company.sqlite3')
            try:
                window = AIWACKWindow(root, store)
                window.account_name.set('preview-owner')
                window.account_password.set('preview-owner-password-2026')
                window.password_confirm.set('preview-owner-password-2026')
                window.auth_button.invoke()
                root.update()
                assert store.is_authenticated
                assert window.research_bundle_button.winfo_exists()

                # A cancelled confirmation must not insert any row.
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno', return_value=False) as approval:
                    window.research_bundle_button.invoke()
                    approval.assert_called_once()
                root.update()
                assert '등록 취소' in window.research_feedback.get()
                assert '가져오기 전 점검' in window.research_detail.get('1.0', 'end')
                assert not store.search_offline_research()

                # File tampering while the approval box is open must fail closed.
                def change_during_approval(*args, **kwargs):
                    contents.write_text('Changed after preview', encoding='utf-8')
                    return True
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno', side_effect=change_during_approval):
                    window.research_bundle_button.invoke()
                root.update()
                assert '다시 검토' in window.research_feedback.get(), window.research_feedback.get()
                assert not store.search_offline_research()

                # Actual reviewed state, after re-preview, imports successfully.
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno', return_value=True):
                    window.research_bundle_button.invoke()
                root.update()
                assert '1건 등록' in window.research_feedback.get(), window.research_feedback.get()
                assert len(store.search_offline_research()) == 1

                # Existing duplicate is blocked before confirmation prompt.
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno') as approval:
                    window.research_bundle_button.invoke()
                    approval.assert_not_called()
                assert '가져오기 차단' in window.research_feedback.get()
                window.sign_out()
                root.update()
            finally:
                root.destroy()
    print('PASS: Tkinter preview cancel, tamper-while-confirming, import, duplicate, offline')


if __name__ == '__main__':
    main()
