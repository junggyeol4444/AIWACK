"""Real Tkinter JSON export button with no network or interactive save dialog."""
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore
from desktop.research_exports import verify_evidence_export


def deny(*args, **kwargs):
    raise AssertionError('network access forbidden')


def main():
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    socket.create_connection = deny
    with tempfile.TemporaryDirectory(prefix='aiwack-export-gui-') as folder:
        db = Path(folder) / 'owner.sqlite3'
        destination = Path(folder) / 'report.json'
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(db))
            app.account_name.set('export-gui-owner')
            app.account_password.set('export-password-2026')
            app.password_confirm.set('export-password-2026')
            app.auth_button.invoke()
            root.update()
            assert app.store.is_authenticated
            record = app.store.add_offline_research('https://example.org/one',
                                                     'local', 'line one\n한국어 export')
            app.research_query.set('한국어')
            assert app.research_export_button.winfo_exists()
            with patch('desktop.app.filedialog.asksaveasfilename', return_value=str(destination)):
                app.research_export_button.invoke()
            root.update()
            assert f'#{record}' not in app.research_feedback.get()  # status, not report body
            assert '저장:' in app.research_feedback.get()
            report = verify_evidence_export(destination.read_bytes())
            assert report['hits'][0]['capture_id'] == record
            assert report['source_authenticity_verified'] is False
            # Repeating with the same path must never replace existing file.
            old = destination.read_bytes()
            with patch('desktop.app.filedialog.asksaveasfilename', return_value=str(destination)):
                app.research_export_button.invoke()
            root.update()
            assert '실패' in app.research_feedback.get()
            assert destination.read_bytes() == old
            app.sign_out()
            root.update()
        finally:
            root.destroy()
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(db))
            app.account_name.set('export-gui-owner')
            app.account_password.set('export-password-2026')
            app.auth_button.invoke()
            root.update()
            assert app.store.is_authenticated
            app.research_query.set('한국어')
            with patch('desktop.app.filedialog.asksaveasfilename', return_value=str(Path(folder) / 'second.json')):
                app.research_export_button.invoke()
            root.update()
            assert '저장:' in app.research_feedback.get()
            print('PASS real Tkinter export + no overwrite + restart + socket blocked')
        finally:
            root.destroy()

if __name__ == '__main__':
    main()
