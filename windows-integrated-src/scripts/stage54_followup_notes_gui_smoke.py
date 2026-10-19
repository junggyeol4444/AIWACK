"""Run under Xvfb; real Tkinter button clicks, no network."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import socket
import tempfile
import tkinter as tk

from desktop.storage import LocalStore
from desktop.app import AIWACKWindow


def denied(*args, **kwargs):
    raise AssertionError('Unexpected network access')

socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied

with tempfile.TemporaryDirectory() as directory:
    db = Path(directory) / 'gui.sqlite3'
    store = LocalStore(db)
    store.setup_owner('gui-triage', 'gui-triage-password-2026')
    store.add_offline_research('https://example.org/root', 'Root',
        '<p>Saved</p><a href="/follow">Follow</a>', 'html_snapshot')
    root = tk.Tk()
    root.withdraw()
    app = AIWACKWindow(root, store)
    app._enter_dashboard()
    root.update_idletasks()
    assert app.research_followup_note_button.winfo_exists()
    app.research_followup_url.set('https://example.org/follow')
    app.research_followup_action.set('deferred')
    app.research_followup_note.set('Review later with owner')
    app.research_followup_note_button.invoke()
    assert '저장' in app.research_feedback.get(), app.research_feedback.get()
    assert store.offline_research_followup_history('https://example.org/follow')['items'][0]['action'] == 'deferred'
    app.research_followup_history_button.invoke()
    assert 'Review later with owner' in app.research_detail.get('1.0','end')
    app.research_followup_button.invoke()
    assert 'deferred' in app.research_detail.get('1.0','end')
    app.sign_out()
    app.account_name.set('gui-triage')
    app.account_password.set('gui-triage-password-2026')
    app.submit_login()
    app.research_followup_url.set('https://example.org/follow')
    app.research_followup_history_button.invoke()
    assert 'Review later with owner' in app.research_detail.get('1.0','end')
    root.destroy()
print('GUI PASS: real buttons, logout/login, SQLite persistence, sockets blocked')
