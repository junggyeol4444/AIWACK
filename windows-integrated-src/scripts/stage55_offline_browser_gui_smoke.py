"""Actual Tkinter login and browser button click, with no user-PC changes."""
from pathlib import Path
import tempfile
import tkinter as tk

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore
from desktop.offline_browser import installed_chromium


def main():
    with tempfile.TemporaryDirectory(prefix='aiwack-stage55-gui-') as temp:
        db=Path(temp)/'temp.sqlite3'
        doc=Path(temp)/'offline.html'
        doc.write_text('<title>테스트 문서</title><p>Offline Alpha Alpha</p>'
                       '<script>document.title="not allowed"</script>',encoding='utf-8')
        root=tk.Tk()
        try:
            app=AIWACKWindow(root, LocalStore(db))
            app.account_name.set('stage55owner')
            app.account_password.set('long-local-password-55')
            app.password_confirm.set('long-local-password-55')
            app.auth_button.invoke();root.update()
            assert app.store.is_authenticated
            assert '허용된 로컬 브라우저 작업' in app.quick_navigation['values']
            app.browser_html_path.set(str(doc))
            app.browser_find_text.set('alpha')
            app.browser_run_button.invoke();root.update()
            response=app.browser_feedback.get()
            if installed_chromium():
                assert '검색 일치: 2회' in response, response
                assert 'not allowed' not in response
            else:
                assert '없어' in response or '실패' in response
            app.sign_out();root.update()
            app._run_offline_browser_task()
            assert '거부' in app.browser_feedback.get(), app.browser_feedback.get()
        finally:
            root.destroy()
        assert db.is_file()
    print('PASS Stage55: owner-only offline Chromium read/find GUI, logout deny, temporary DB')

if __name__=='__main__':main()
