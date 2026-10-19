"""Owner UI smoke: ambiguous research JSON must fail closed, without network."""
import json
import socket
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def denied(*args, **kwargs):
    raise AssertionError('network forbidden')


def main():
    with patch.object(socket.socket, 'connect', denied), \
         patch.object(socket.socket, 'sendto', denied), \
         patch.object(socket, 'getaddrinfo', denied):
        with tempfile.TemporaryDirectory(prefix='aiwack-duplicate-keys-') as directory:
            base = Path(directory)
            (base / 'evidence.txt').write_text('Local research material', encoding='utf-8')
            manifest = base / 'bundle.json'
            manifest.write_text(json.dumps({
                'format': 'aiwack-offline-research-bundle-v1',
                'items': [{'file': 'evidence.txt', 'url': 'https://example.org/e', 'title': 'Evidence'}]
            }), encoding='utf-8')
            store = LocalStore(base / 'company.sqlite3')
            root = tk.Tk()
            try:
                app = AIWACKWindow(root, store)
                app.account_name.set('owner')
                app.account_password.set('owner-password-2026')
                app.password_confirm.set('owner-password-2026')
                app.auth_button.invoke()
                root.update()
                assert store.is_authenticated
                baseline = store.path.read_bytes()
                malformed = manifest.read_text(encoding='utf-8').replace(
                    '"url":', '"url":"https://other.example/", "url":', 1)
                manifest.write_text(malformed, encoding='utf-8')
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno') as approval:
                    app.research_bundle_button.invoke()
                    approval.assert_not_called()
                root.update()
                assert '중복된 키' in app.research_feedback.get(), app.research_feedback.get()
                assert not store.search_offline_research()
                assert store.path.read_bytes() == baseline

                # Good manifest still works, custody receipt still verifies.
                manifest.write_text(json.dumps({
                    'format': 'aiwack-offline-research-bundle-v1',
                    'items': [{'file': 'evidence.txt', 'url': 'https://example.org/e', 'title': 'Evidence'}]
                }), encoding='utf-8')
                receipt = base / 'receipt.json'
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno', return_value=True), \
                     patch('desktop.app.filedialog.asksaveasfilename', return_value=str(receipt)):
                    app.research_receipt_create_button.invoke()
                assert receipt.exists()
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(receipt)):
                    app.research_receipt_verify_button.invoke()
                assert '일치' in app.research_feedback.get(), app.research_feedback.get()

                payload = receipt.read_text(encoding='utf-8')
                receipt.write_text(payload.replace('"raw_size":', '"raw_size": 1, "raw_size":', 1), encoding='utf-8')
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(receipt)):
                    app.research_receipt_verify_button.invoke()
                assert '중복된 키' in app.research_feedback.get(), app.research_feedback.get()
                assert store.path.read_bytes() == baseline
                print('PASS: Tkinter rejected duplicate manifest/receipt keys; valid receipt passed; DB unchanged')
            finally:
                root.destroy()


if __name__ == '__main__':
    main()
