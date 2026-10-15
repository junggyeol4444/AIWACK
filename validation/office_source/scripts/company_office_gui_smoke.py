"""Actually instantiate the desktop UI and exercise cockpit navigation and actions."""
import tempfile
from pathlib import Path
import tkinter as tk
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore

with tempfile.TemporaryDirectory() as directory:
    root = tk.Tk()
    try:
        db = LocalStore(Path(directory) / 'user.sqlite3')
        window = AIWACKWindow(root, db)
        window.account_name.set('company_owner')
        window.account_password.set('safe-owner-password-2026')
        window.password_confirm.set('safe-owner-password-2026')
        window.submit_setup()
        root.update()
        office = window.company_office
        assert window.tabs.tab(0, 'text') == 'AI 회사 운영센터'
        assert office.view_name == 'overview'
        assert '미지정' in office.chief_label.get()
        assert office.cards['tasks'].get() == '0'
        for page in ('organization', 'work', 'results', 'overview', 'work'):
            office.nav_buttons[page].invoke()
            root.update()
            assert office.view_name == page
            assert office.views[page].winfo_viewable()
        # Check the real Tk window stays inside its default 1040x720 bounds.
        assert office.task_entry.winfo_viewable()
        assert office.task_entry.winfo_rooty() + office.task_entry.winfo_height() <= (
            root.winfo_rooty() + root.winfo_height())
        office.title.set('First genuine AI company task')
        office.create()
        root.update()
        assert db.list_tasks()[0]['title'] == 'First genuine AI company task'
        assert len(office.jobs.get_children()) == len(office.work_jobs.get_children()) == 1
        assert office.cards['tasks'].get() == '1'
        assert db.list_task_runs() == []
        office.set_view('results')
        root.update()
        assert office.cards['pending'].get() == '0'
        print('COMPANY_OFFICE_LIVE_GUI_PASS')
    finally:
        root.destroy()
