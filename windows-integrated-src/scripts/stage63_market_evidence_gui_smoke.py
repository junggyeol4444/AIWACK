"""Stage63 real Tk GUI smoke (Linux Xvfb is not Windows verification)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import socket
import tkinter as tk
from unittest.mock import patch

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main():
    def forbidden(*args, **kwargs):
        raise AssertionError('network forbidden')
    with TemporaryDirectory(prefix='aiwack63-gui-') as tmp, \
         patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(Path(tmp) / 'owner.sqlite3'))
            app.account_name.set('owner63')
            app.account_password.set('stage63-long-password')
            app.password_confirm.set('stage63-long-password')
            app.auth_button.invoke(); root.update()
            assert '시장 수요·경쟁 근거 검토' in app.quick_navigation['values']
            candidate = app.store.generate_business_candidates('고객', '문제', 1)['created_ids'][0]
            capture = app.store.add_offline_research('https://example.org/local-claim', '주장',
                '일부 고객은 편의성을 원한다고 주장했다. 실제 수요는 아직 미확인이다.')
            app.market_candidate_id.set(str(candidate))
            app.market_capture_id.set(str(capture))
            app.market_kind.set('demand')
            app.market_stance.set('supports')
            app.market_excerpt.set('일부 고객은 편의성을 원한다고 주장했다.')
            app.market_note.set('수동 인용 검토')
            with patch('desktop.app.messagebox.askyesno', return_value=False):
                app.market_link_button.invoke(); root.update()
            assert app.store.market_evidence(candidate) == []
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app.market_link_button.invoke(); root.update()
            assert len(app.store.market_evidence(candidate)) == 1
            assert '검증 없음' in app.market_feedback.get()
            app.market_tree.selection_set(app.market_tree.get_children()[0]); root.update()
            assert int(app.market_link_id.get()) > 0
            with patch('desktop.app.messagebox.askyesno', return_value=True):
                app.market_review_button.invoke(); root.update()
            assert app.store.market_evidence(candidate)[0]['review'] == 'noted'
            app.market_events_button.invoke(); root.update()
            assert 'review_changed' in app.market_feedback.get()
            app.sign_out(); root.update()
            app._market_refresh(); root.update()
            assert '거부' in app.market_feedback.get()
        finally:
            root.destroy()
    print('PASS Stage63 Tk: owner, cancel, link, review, audit, logout denial; no sockets/DNS')


if __name__ == '__main__':
    main()
