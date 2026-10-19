"""Actual native Tkinter follow-up pagination smoke test (run under Xvfb)."""
import socket
import tempfile
import tkinter as tk
from pathlib import Path
from desktop.storage import LocalStore
from desktop.app import AIWACKWindow


def denied(*args, **kwargs):
    raise AssertionError('Network access attempted')

socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied

with tempfile.TemporaryDirectory() as td:
    store = LocalStore(Path(td) / 'owner.sqlite3')
    store.setup_owner('owner-test', 'owner-password-2026')
    html = '<p>Saved locally</p>' + ''.join(
        f'<a href="/link-{n:03}">link</a>' for n in range(90))
    store.add_offline_research('https://example.org/index', 'index', html, 'html_snapshot')
    store.logout()
    root = tk.Tk()
    root.withdraw()
    window = AIWACKWindow(root, store)
    window.account_name.set('owner-test')
    window.account_password.set('owner-password-2026')
    window.submit_login()
    assert hasattr(window, 'research_followup_next_button')
    for tab_id in window.tabs.tabs():
        if window.tabs.tab(tab_id, 'text') == '오프라인 조사 자료 수집':
            window.tabs.select(tab_id)
            break
    root.deiconify()
    root.update_idletasks()
    assert window.research_followup_next_button.winfo_ismapped()
    assert window.research_followup_prev_button.winfo_ismapped()
    window.research_followup_button.invoke()
    assert window.research_followup_page == 1
    assert '페이지 1/3' in window.research_detail.get('1.0', 'end')
    window.research_followup_next_button.invoke()
    assert window.research_followup_page == 2
    assert '페이지 2/3' in window.research_detail.get('1.0', 'end')
    window.research_followup_next_button.invoke()
    assert window.research_followup_page == 3
    assert '페이지 3/3' in window.research_detail.get('1.0', 'end')
    window.research_followup_next_button.invoke()
    assert window.research_followup_page == 3
    window.research_followup_prev_button.invoke()
    assert window.research_followup_page == 2
    # Changing manual review filter resets page to one.
    window.research_review_filter.set('deferred')
    window.research_review_filter_combo.event_generate('<<ComboboxSelected>>')
    assert window.research_followup_page == 1
    assert '필터 결과 0개' in window.research_detail.get('1.0', 'end')
    # Append-only note and new filtered list persist through logout/login.
    window.research_followup_url.set('https://example.org/link-080')
    window.research_followup_action.set('deferred')
    window.research_followup_note.set('Manual offline follow-up')
    window.research_followup_note_button.invoke()
    assert '필터 결과 1개' in window.research_detail.get('1.0', 'end')
    window.sign_out()
    window.account_name.set('owner-test')
    window.account_password.set('owner-password-2026')
    window.submit_login()
    window.research_review_filter.set('deferred')
    window.research_followup_button.invoke()
    assert '필터 결과 1개' in window.research_detail.get('1.0', 'end')
    root.destroy()
print('PASS: real Tkinter previous/next/filter/relogin; sockets blocked')
