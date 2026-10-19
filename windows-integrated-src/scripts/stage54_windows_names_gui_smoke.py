"""Smoke test of actual Tkinter manifest button with Windows filename rules."""
import os
from pathlib import Path
import socket
import tempfile
import tkinter as tk
from unittest.mock import patch

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def deny(*_args, **_kwargs):
    raise AssertionError('network access forbidden')


def main():
    with patch.object(socket.socket, 'connect', deny), \
         patch.object(socket.socket, 'sendto', deny), \
         patch.object(socket, 'getaddrinfo', deny):
        with tempfile.TemporaryDirectory(prefix='aiwack-win-names-') as tmp:
            folder = Path(tmp)
            valid = folder / '보고서.txt'
            valid.write_text('Offline investigation', encoding='utf-8')
            reserved = folder / 'CON.txt'
            if os.name != 'nt':
                reserved.write_text('Unportable source name', encoding='utf-8')
            destination = folder / 'bundle.json'
            store = LocalStore(folder / 'local.sqlite3')
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

                def click(selected):
                    with patch('desktop.app.filedialog.askopenfilenames', return_value=(str(selected),)), \
                         patch('desktop.app.simpledialog.askstring', side_effect=[
                             'https://example.org/a', 'Document']), \
                         patch('desktop.app.messagebox.askyesno', return_value=True), \
                         patch('desktop.app.filedialog.asksaveasfilename', return_value=str(destination)):
                        app.research_bundle_manifest_button.invoke()
                        root.update()

                if reserved.exists() and os.name != 'nt':
                    click(reserved)
                    assert not destination.exists()
                    assert '예약' in app.research_feedback.get()
                click(valid)
                assert destination.exists()
                assert '아직 SQLite 등록 없음' in app.research_feedback.get()
                assert not store.search_offline_research()
                assert store.path.read_bytes() == baseline
                print('PASS Tkinter: Windows-unportable name rejected, valid bundle created; DB/network untouched')
            finally:
                root.destroy()


if __name__ == '__main__':
    main()
