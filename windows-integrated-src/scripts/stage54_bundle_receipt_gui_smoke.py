"""Real Tkinter controls: local receipt creation and read-only verification."""
import json
import socket
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import patch
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def deny(*args, **kwargs):
    raise AssertionError('network unavailable')


def main():
    with patch.object(socket.socket,'connect',deny), patch.object(socket.socket,'sendto',deny), \
         patch.object(socket,'getaddrinfo',deny):
        with tempfile.TemporaryDirectory(prefix='aiwack-receipt-') as directory:
            folder=Path(directory)
            source=folder/'source.txt';source.write_text('Local offline evidence',encoding='utf-8')
            manifest=folder/'bundle.json'
            receipt=folder/'receipt.json'
            store=LocalStore(folder/'store.sqlite')
            store.setup_owner('owner','owner-password')
            store.create_offline_research_bundle_manifest(
                [(source,'https://example.org/source','Local evidence')],manifest)
            root=tk.Tk()
            try:
                app=AIWACKWindow(root,store)
                app.account_name.set('owner')
                app.account_password.set('owner-password')
                app.auth_button.invoke();root.update()
                assert store.is_authenticated
                with patch('desktop.app.filedialog.askopenfilename',return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno',return_value=False):
                    app.research_receipt_create_button.invoke()
                assert not receipt.exists()
                with patch('desktop.app.filedialog.askopenfilename',return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno',return_value=True), \
                     patch('desktop.app.filedialog.asksaveasfilename',return_value=str(receipt)):
                    app.research_receipt_create_button.invoke()
                assert receipt.exists()
                with patch('desktop.app.filedialog.askopenfilename',return_value=str(receipt)):
                    app.research_receipt_verify_button.invoke()
                assert '지문 재검사 일치' in app.research_feedback.get()
                source.write_text('Altered evidence',encoding='utf-8')
                with patch('desktop.app.filedialog.askopenfilename',return_value=str(receipt)):
                    app.research_receipt_verify_button.invoke()
                assert '불일치' in app.research_feedback.get()
                assert 'changed' in app.research_detail.get('1.0','end')
                assert not store.search_offline_research()
                # Simulate a file changing after the initial SHA-256 read but
                # before a receipt is emitted. The real GUI must reject it.
                import desktop.research_bundle_manifest as bundle_module
                original_reader = bundle_module.read_local_snapshot
                altered = {'done': False}
                guarded_receipt = folder / 'guarded-receipt.json'

                def change_after_read(path):
                    result = original_reader(path)
                    if not altered['done']:
                        altered['done'] = True
                        source.write_text('Changed while scanning', encoding='utf-8')
                    return result

                with patch('desktop.research_bundle_manifest.read_local_snapshot', side_effect=change_after_read), \
                     patch('desktop.app.filedialog.askopenfilename', return_value=str(manifest)), \
                     patch('desktop.app.messagebox.askyesno', return_value=True), \
                     patch('desktop.app.filedialog.asksaveasfilename', return_value=str(guarded_receipt)):
                    app.research_receipt_create_button.invoke()
                assert altered['done'] and not guarded_receipt.exists()
                assert '변경' in app.research_feedback.get()
                assert not store.search_offline_research()
                print('PASS receipt Tkinter cancel/create/match/change/concurrent-change refusal, no DB writes or network')
            finally:
                root.destroy()


if __name__=='__main__':
    main()
