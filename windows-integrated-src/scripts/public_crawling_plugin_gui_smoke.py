"""Validate the native admin screen for direct crawling and plugin import in Xvfb."""
import json
from pathlib import Path
import tkinter as tk
from tempfile import TemporaryDirectory
from unittest.mock import patch

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    with TemporaryDirectory(prefix='aiwack-crawl-gui-') as tmp:
        root=tk.Tk()
        try:
            app=AIWACKWindow(root,LocalStore(Path(tmp)/'user.sqlite3'))
            app.account_name.set('crawl_owner')
            app.account_password.set('secure-crawl-owner-password')
            app.password_confirm.set('secure-crawl-owner-password')
            app.auth_button.invoke(); root.update()
            assert app.store.has_owner()
            assert app.research_crawl_button.winfo_exists()
            assert app.research_plugin_import_button.winfo_exists()
            app.research_url.set('https://docs.python.org/3/library/urllib.request.html')
            app.research_online_confirm_host.set('docs.python.org')
            app.research_crawl_button.invoke(); root.update()
            assert '허용을 확인' in app.research_feedback.get()
            app.research_online_consent.set(True)
            source=(Path(__file__).resolve().parents[1]/'docs'/'verification_public_crawling_plugin_20261015'/'tinyfish_live_excerpts.json')
            with patch('desktop.app.filedialog.askopenfilename',return_value=str(source)):
                app.research_plugin_import_button.invoke(); root.update()
            assert '2건' in app.research_feedback.get()
            assert len(app.store.search_offline_research('urllib')) >= 1
            # Use mocked network only for local Xvfb UI smoke.
            def fake_crawl(*args,**kwargs):
                return {'pages':2,'failures':0,'capture_ids':[], 'robots_checked':True}
            with patch.object(app.store,'crawl_public_site_robots_checked',side_effect=fake_crawl):
                app.research_crawl_button.invoke()
                import time
                for _ in range(40):
                    root.update()
                    if '2건 수집' in app.research_feedback.get():break
                    time.sleep(.02)
                print('GUI CRAWL FEEDBACK:',repr(app.research_feedback.get()))
                assert 'robots.txt 확인' in app.research_feedback.get() and '2건 수집' in app.research_feedback.get()
            app.sign_out(); root.update()
            with patch('desktop.app.filedialog.askopenfilename',return_value=str(source)):
                app._import_web_plugin_export(); root.update()
            assert '실패' in app.research_feedback.get()
        finally:
            root.destroy()
    print('PASS owner-click crawler + portable plugin import GUI, logout protection (crawl transport mocked)')

if __name__=='__main__':main()
