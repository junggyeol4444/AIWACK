"""Stage60 actual Tk GUI: failure record, cancellation, review, logout."""
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from unittest.mock import patch

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    with TemporaryDirectory(prefix='aiwack60-gui-') as tmp:
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(Path(tmp)/'owner.sqlite3'))
            app.account_name.set('owner60')
            app.account_password.set('stage60-owner-long-password')
            app.password_confirm.set('stage60-owner-long-password')
            app.auth_button.invoke(); root.update()
            assert '도구 사용·실패 기록' in app.quick_navigation['values']
            try:
                app.store.prepare_service_draft('invalid','x','x','x')
            except ValueError:
                pass
            event_id = app.store.tool_use_history()[0]['id']
            app.tool_audit_id.set(str(event_id))
            app.tool_audit_refresh_button.invoke(); root.update()
            assert 'service_draft_prepare' in app.tool_audit_feedback.get()
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app.tool_audit_ack_button.invoke(); root.update()
            assert app.store.tool_use_history()[0]['review_state'] == 'unreviewed'
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app.tool_audit_ack_button.invoke(); root.update()
                app.tool_audit_resolve_button.invoke(); root.update()
            assert app.store.tool_use_history()[0]['review_state'] == 'resolved'
            app.sign_out(); root.update()
            app._tool_audit_refresh(); root.update()
            assert '거부' in app.tool_audit_feedback.get()
        finally:
            root.destroy()
    print('PASS Stage60 GUI: history, cancellation, acknowledge, resolve, logout denied')


if __name__ == '__main__':
    main()
