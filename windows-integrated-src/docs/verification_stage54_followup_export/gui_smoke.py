"""Actual Tkinter local JSON export interaction, under Linux Xvfb."""
import socket
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

from desktop.storage import LocalStore
from desktop.app import AIWACKWindow
from desktop.research_followup_exports import verify_followup_export


def denied(*args, **kwargs):
    raise AssertionError('Unexpected network call')

socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied

with tempfile.TemporaryDirectory() as td:
    db = LocalStore(Path(td) / 'test.sqlite3')
    db.setup_owner('local-owner', 'password-for-local-owner')
    html = '<p>offline</p>' + ''.join(
        f'<a href="/item-{n:03}">link</a>' for n in range(83))
    db.add_offline_research('https://example.org/index', 'Offline', html, 'html_snapshot')
    db.logout()
    root = tk.Tk()
    root.withdraw()
    app = AIWACKWindow(root, db)
    app.account_name.set('local-owner')
    app.account_password.set('password-for-local-owner')
    app.submit_login()
    for tab_id in app.tabs.tabs():
        if app.tabs.tab(tab_id, 'text') == '오프라인 조사 자료 수집':
            app.tabs.select(tab_id)
            break
    root.deiconify()
    root.update_idletasks()
    assert app.research_followup_export_button.winfo_exists()
    app.research_followup_next_button.invoke()
    assert app.research_followup_page == 2
    path = Path(td) / 'all-links.json'
    with patch('desktop.app.filedialog.asksaveasfilename', return_value=str(path)):
        app.research_followup_export_button.invoke()
    report = verify_followup_export(path.read_bytes())
    assert len(report['items']) == 83, 'Must export all pages, not only visible 40'
    assert '후속 조사 JSON 저장' in app.research_feedback.get()
    # Existing destination must remain untouched on second attempt.
    before = path.read_bytes()
    with patch('desktop.app.filedialog.asksaveasfilename', return_value=str(path)):
        app.research_followup_export_button.invoke()
    assert path.read_bytes() == before
    assert '저장 실패' in app.research_feedback.get()
    app.sign_out()
    app.account_name.set('local-owner')
    app.account_password.set('password-for-local-owner')
    app.submit_login()
    assert app.research_followup_export_button.winfo_exists()
    root.destroy()
print('PASS: real Tkinter button, all pages exported, overwrite blocked, relogin, socket blocked')
