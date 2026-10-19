"""Native GUI file-byte recheck including mismatch and relogin, offline only."""
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
    raise AssertionError('network access forbidden')


def main():
    for name in ('connect', 'connect_ex', 'sendto', 'sendall'):
        setattr(socket.socket, name, deny)
    socket.getaddrinfo = deny
    with tempfile.TemporaryDirectory(prefix='aiwack-custody-') as folder:
        file = Path(folder) / 'original.txt'
        file.write_bytes(b'locally archived source material')
        db = Path(folder) / 'database.sqlite3'
        for first in (True, False):
            root = tk.Tk()
            try:
                app = AIWACKWindow(root, LocalStore(db))
                app.account_name.set('custody-owner')
                app.account_password.set('passphrase-2026-long')
                if first:
                    app.password_confirm.set('passphrase-2026-long')
                app.auth_button.invoke()
                root.update()
                assert app.store.is_authenticated
                if first:
                    capture_id = app.store.import_offline_research_file(
                        'https://example.org/source', 'Source', file)
                app.research_selected_id = capture_id
                assert app.research_file_custody_button.winfo_exists()
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(file)):
                    app.research_file_custody_button.invoke()
                root.update()
                assert '파일 바이트 SHA-256 일치: 예' in app.research_detail.get('1.0', 'end')
                assert '파일 바이트 일치' in app.research_feedback.get()
                if first:
                    file.write_bytes(b'changed local source')
                    with patch('desktop.app.filedialog.askopenfilename', return_value=str(file)):
                        app.research_file_custody_button.invoke()
                    root.update()
                    assert '파일 바이트 SHA-256 일치: 아니오' in app.research_detail.get('1.0', 'end')
                    assert '다릅니다' in app.research_feedback.get()
                    file.write_bytes(b'locally archived source material')
                app.sign_out()
                root.update()
            finally:
                root.destroy()
    print('PASS Tkinter local-file custody match/mismatch/relogin, sockets blocked')


if __name__ == '__main__':
    main()
