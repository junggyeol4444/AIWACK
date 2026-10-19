"""Real native Tkinter review filter workflow under Xvfb, sockets blocked."""
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
    db = Path(directory) / 'review_filter.sqlite3'
    store = LocalStore(db)
    store.setup_owner('review-filter', 'review-filter-password-2026')
    store.add_offline_research('https://example.org/root', 'Root',
        '<p>Saved</p><a href="/deferred">Deferred</a><a href="/pending">Pending</a>',
        'html_snapshot')
    root = tk.Tk()
    root.withdraw()
    app = AIWACKWindow(root, store)
    app._enter_dashboard()
    root.update_idletasks()
    assert app.research_review_filter_combo.winfo_exists()
    app.research_followup_url.set('https://example.org/deferred')
    app.research_followup_action.set('deferred')
    app.research_followup_note.set('Manual deferral, not verified')
    app.research_followup_note_button.invoke()
    app.research_review_filter.set('pending')
    app.research_followup_button.invoke()
    detail = app.research_detail.get('1.0', 'end')
    assert 'https://example.org/pending' in detail
    assert 'https://example.org/deferred' not in detail
    app.research_review_filter.set('deferred')
    app.research_followup_button.invoke()
    detail = app.research_detail.get('1.0', 'end')
    assert 'https://example.org/deferred' in detail
    assert 'https://example.org/pending' not in detail
    app.sign_out()
    app.account_name.set('review-filter')
    app.account_password.set('review-filter-password-2026')
    app.submit_login()
    app.research_review_filter.set('deferred')
    app.research_followup_button.invoke()
    assert 'https://example.org/deferred' in app.research_detail.get('1.0', 'end')
    root.destroy()
print('PASS: native Tkinter triage filter, re-login, socket blocked')
