"""Real Tkinter owner-only receipt recheck; simulates an intervening local edit."""
from pathlib import Path
import socket
import tempfile
import tkinter as tk
from unittest.mock import patch

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore
import desktop.research_bundle_manifest as bundle


def _deny(*args, **kwargs):
    raise AssertionError('Network access is forbidden')


def main():
    with patch.object(socket.socket, 'connect', _deny), \
         patch.object(socket.socket, 'sendto', _deny), \
         patch.object(socket, 'getaddrinfo', _deny):
        with tempfile.TemporaryDirectory(prefix='aiwack-recheck-stable-') as dirname:
            root_dir = Path(dirname)
            source1, source2 = root_dir / 'first.txt', root_dir / 'second.txt'
            source1.write_text('One original', encoding='utf-8')
            source2.write_text('Two original', encoding='utf-8')
            manifest, receipt = root_dir / 'bundle.json', root_dir / 'receipt.json'
            store = LocalStore(root_dir / 'local.sqlite')
            store.setup_owner('owner', 'owner-password')
            store.create_offline_research_bundle_manifest([
                (source1, 'https://example.org/a', 'A'),
                (source2, 'https://example.org/b', 'B')], manifest)
            store.create_offline_research_bundle_receipt(manifest, receipt)
            window = tk.Tk()
            try:
                app = AIWACKWindow(window, store)
                app.account_name.set('owner')
                app.account_password.set('owner-password')
                app.auth_button.invoke()
                window.update()
                assert store.is_authenticated
                db_before = store.path.read_bytes()  # login may update local auth metadata
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(receipt)):
                    app.research_receipt_verify_button.invoke()
                assert '일치' in app.research_feedback.get()
                reader = bundle.read_local_snapshot
                scanned = {'n': 0}

                def change_after_early_read(path):
                    value = reader(path)
                    scanned['n'] += 1
                    if scanned['n'] == 2:
                        source1.write_text('Changed mid-verification', encoding='utf-8')
                    return value

                with patch('desktop.research_bundle_manifest.read_local_snapshot', side_effect=change_after_early_read), \
                     patch('desktop.app.filedialog.askopenfilename', return_value=str(receipt)):
                    app.research_receipt_verify_button.invoke()
                assert scanned['n'] == 4
                assert '불일치' in app.research_feedback.get()
                assert '검사 도중' in app.research_detail.get('1.0', 'end')
                assert 'changed' in app.research_detail.get('1.0', 'end')
                assert store.path.read_bytes() == db_before
                print('PASS GUI owner receipt recheck: stable match, midcheck mutation flagged, DB unchanged, no network')
            finally:
                window.destroy()


if __name__ == '__main__':
    main()
