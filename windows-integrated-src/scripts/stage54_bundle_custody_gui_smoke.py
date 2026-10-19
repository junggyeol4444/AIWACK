"""Linux/Xvfb Tk GUI integration: imported local batch files checked offline."""
import socket
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def blocked(*args, **kwargs):
    raise AssertionError('Network operation forbidden')


def main():
    with patch.object(socket.socket, 'connect', blocked), \
         patch.object(socket.socket, 'connect_ex', blocked), \
         patch.object(socket.socket, 'sendall', blocked), \
         patch.object(socket.socket, 'sendto', blocked), \
         patch.object(socket, 'getaddrinfo', blocked):
        with tempfile.TemporaryDirectory(prefix='aiwack-stage54-batch-custody-') as name:
            folder = Path(name)
            sample = folder / 'source.txt'
            sample.write_text('Offline source custody original', encoding='utf-8')
            store = LocalStore(folder / 'local.sqlite3')
            root = tk.Tk()
            try:
                app = AIWACKWindow(root, store)
                app.account_name.set('gui-custody-owner')
                app.account_password.set('gui-custody-password-2026')
                app.password_confirm.set('gui-custody-password-2026')
                app.auth_button.invoke()
                root.update()
                manifest = folder / 'batch.json'
                store.create_offline_research_bundle_manifest([
                    (sample, 'https://example.org/source', 'Source')], manifest)
                preview = store.preview_offline_research_bundle(manifest)
                store.import_offline_research_bundle(manifest,
                    expected_preview_token=preview['preview_token'])
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)):
                    app.research_bundle_custody_button.invoke()
                root.update()
                assert '일괄 검사 통과' in app.research_feedback.get()
                assert '원본 바이트 일치' in app.research_detail.get('1.0', 'end')
                sample.write_text('Different text', encoding='utf-8')
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)):
                    app.research_bundle_custody_button.invoke()
                root.update()
                assert '불일치 발견' in app.research_feedback.get()
                assert '파일 변경됨' in app.research_detail.get('1.0', 'end')
                sample.unlink()
                with patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)):
                    app.research_bundle_custody_button.invoke()
                root.update()
                assert '파일 누락/읽기 불가' in app.research_detail.get('1.0', 'end')
                app.sign_out()
                root.update()
            finally:
                root.destroy()
    print('PASS: actual GUI button batch custody match/changed/missing; sockets and DNS blocked')


if __name__ == '__main__':
    main()
