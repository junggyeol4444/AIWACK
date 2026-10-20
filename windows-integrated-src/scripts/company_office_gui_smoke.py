"""Actually instantiate the desktop UI and exercise cockpit navigation and actions."""
import tempfile
from pathlib import Path
import tkinter as tk
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
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
        for page in ('organization', 'planning', 'work', 'results', 'overview', 'work'):
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

        # Verify ALL owner controls remain visible inside the actual GUI, not
        # merely present in the Tk object tree. A moved approval button broke
        # the physical Windows mouse E2E even though headless tests passed.
        def find_button(widget, title):
            for child in widget.winfo_children():
                if isinstance(child, tk.Button) and child.cget('text') == title:
                    return child
                found=find_button(child,title)
                if found is not None:
                    return found
            return None
        for view,labels in [
            ('work',['비상 정지','31명 승인 연속 운영','운영 기록 확인']),
            ('results',['승인','수정 요청','반려','결과물 품질 검사','승인 결과 파일 저장']),
            ('overview',['회사 DB 백업','백업 무결성 확인',
                         '검증된 회사 백업의 별도 복구 사본 만들기']),
        ]:
            office.set_view(view)
            root.update()
            for label in labels:
                button=find_button(root,label)
                assert button is not None, f'Missing real GUI button: {label}'
                assert button.winfo_viewable(), f'Invisible real GUI button: {label}'
                assert button.winfo_rootx() >= root.winfo_rootx()
                assert button.winfo_rooty() >= root.winfo_rooty()
                assert button.winfo_rootx()+button.winfo_width() <= root.winfo_rootx()+root.winfo_width(), label
                assert button.winfo_rooty()+button.winfo_height() <= root.winfo_rooty()+root.winfo_height(), label
        print('AIWACK_NEW_OWNER_CONTROLS_ACTUALLY_VISIBLE_PASS')
        print('COMPANY_OFFICE_LIVE_GUI_PASS')
    finally:
        root.destroy()
