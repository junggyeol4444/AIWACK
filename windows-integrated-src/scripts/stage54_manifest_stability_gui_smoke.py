"""Stage54 native Tkinter: manifest writer detects changed file before output."""
from pathlib import Path
import socket
import tempfile
import tkinter as tk
from unittest.mock import patch

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore
import desktop.research_bundle_manifest as module


def deny(*_args, **_kwargs):
    raise AssertionError('network forbidden')


def main():
    with patch.object(socket.socket, 'connect', deny), \
         patch.object(socket.socket, 'sendto', deny), \
         patch.object(socket, 'getaddrinfo', deny):
        with tempfile.TemporaryDirectory(prefix='aiwack-manifest-stability-') as dirname:
            folder = Path(dirname)
            first, second = folder/'a.txt', folder/'b.txt'
            first.write_text('Original A', encoding='utf-8')
            second.write_text('Original B', encoding='utf-8')
            destination = folder/'bundle.json'
            store = LocalStore(folder/'company.sqlite3')
            window = tk.Tk()
            try:
                app = AIWACKWindow(window, store)
                app.account_name.set('owner')
                app.account_password.set('owner-password-2026')
                app.password_confirm.set('owner-password-2026')
                app.auth_button.invoke()
                window.update()
                assert store.is_authenticated
                baseline = store.path.read_bytes()
                original_read = module.read_local_snapshot
                calls = {'n': 0}

                def edit_during_scan(path):
                    value = original_read(path)
                    calls['n'] += 1
                    if calls['n'] == 2:
                        first.write_text('Changed while building', encoding='utf-8')
                    return value

                def invoke_with_dialogs():
                    with patch('desktop.app.filedialog.askopenfilenames', return_value=(str(first), str(second))), \
                         patch('desktop.app.simpledialog.askstring', side_effect=[
                             'https://example.org/a', 'A', 'https://example.org/b', 'B']), \
                         patch('desktop.app.messagebox.askyesno', return_value=True), \
                         patch('desktop.app.filedialog.asksaveasfilename', return_value=str(destination)):
                        app.research_bundle_manifest_button.invoke()
                        window.update()

                with patch('desktop.research_bundle_manifest.read_local_snapshot', side_effect=edit_during_scan):
                    invoke_with_dialogs()
                assert calls['n'] >= 3
                assert not destination.exists()
                assert '자료 파일이 변경' in app.research_feedback.get()
                assert store.path.read_bytes() == baseline
                invoke_with_dialogs()
                assert destination.exists()
                assert '아직 SQLite 등록 없음' in app.research_feedback.get()
                assert not store.search_offline_research()
                assert store.path.read_bytes() == baseline
                print('PASS: Tkinter prevented changed-source manifest, fresh retry succeeded; DB/network untouched')
            finally:
                window.destroy()


if __name__ == '__main__':
    main()
