"""Native Tk Stage29 smoke: two independent offline CLI processes and separate drafts."""
from pathlib import Path
import tempfile
import time
import tkinter as tk
from tkinter import messagebox

from desktop.app import AIWACKWindow
from desktop.model_runtime import ModelConfig
from desktop.storage import LocalStore


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='aiwack-stage29-gui-') as temp:
        base = Path(temp)
        store = LocalStore(base/'stage29.sqlite3')
        root = tk.Tk()
        old_confirm = messagebox.askyesno
        try:
            app = AIWACKWindow(root, store)
            app.account_name.set('owner29')
            app.account_password.set('strong-password-stage29')
            app.password_confirm.set('strong-password-stage29')
            app.auth_button.invoke()
            root.update()
            assert store.is_authenticated
            runner = base/'offline-cli'
            runner.write_text('#!/usr/bin/env python3\nimport time,sys\ntime.sleep(.75)\nprint("GUI29_RESULT " + " ".join(sys.argv[1:]))\n', encoding='utf-8')
            runner.chmod(0o700)
            gguf = base/'fixture.gguf'
            gguf.write_bytes(b'GGUF\x03\x00\x00\x00')
            model = store.add_local_model(ModelConfig('gui-29','llama_cpp',str(runner),str(gguf),8))
            tasks = []
            for index in (1,2):
                department = store.add_department(f'병렬 GUI 팀{index}')
                employee = store.add_employee_draft(f'parallel_gui_{index}',f'AI {index}',department_id=department)
                store.set_employee_model(employee,model)
                task = store.add_task(f'GUI29 TASK {index}',f'OFFLINE {index}')
                store.save_task_requirements(task,department,None)
                assert store.auto_assign_task(task)['employee_id'] == employee
                tasks.append(task)
            app.tabs.select(17)
            root.update()
            messagebox.askyesno = lambda *args, **kwargs: True
            for task in tasks:
                app.task_execution_task.set(next(k for k,v in app.task_execution_map.items() if v==task))
                app.load_task_execution()
                app.task_execution_run_button.invoke()
            assert len(app._task_runs_live) == 2, app.task_execution_feedback.get()
            started = time.monotonic()
            while time.monotonic()-started < 4:
                root.update()
                if sum(row['status']=='running' for row in store.list_task_runs()) == 2:
                    break
                time.sleep(.02)
            else:
                raise AssertionError('Two real subprocess reservations did not overlap')
            started = time.monotonic()
            while app._task_runs_live and time.monotonic()-started < 8:
                root.update()
                time.sleep(.02)
            root.update()
            assert not app._task_runs_live, app.task_execution_feedback.get()
            assert all(store.list_task_runs(task)[0]['status']=='success' for task in tasks)
            assert all(store.list_task_artifacts(task)==[] for task in tasks)
            assert len(app._task_drafts) == 2
            for index, task in enumerate(tasks,1):
                app.task_execution_task.set(next(k for k,v in app.task_execution_map.items() if v==task))
                app.load_task_execution()
                body = app.task_execution_output.get('1.0','end-1c')
                assert f'GUI29 TASK {index}' in body
                assert f'GUI29 TASK {3-index}' not in body
                app.save_current_task_draft()
                assert len(store.list_task_artifacts(task))==1, app.task_execution_feedback.get()
                assert f'GUI29 TASK {index}' in store.read_task_artifact(store.list_task_artifacts(task)[0]['id'])['body']
            # Explicit per-task cancellation through the real Tk button.
            # Wait until SQLite has reserved the run before requesting cancel.
            cancel_task = store.add_task('GUI29 CANCEL', 'cancel one subprocess')
            store.save_task_requirements(cancel_task, store.read_employee_record(
                store.read_task_routing(tasks[0])['employee_id'])['department_id'], None)
            assert store.auto_assign_task(cancel_task)['employee_id'] == store.read_task_routing(tasks[0])['employee_id']
            app.refresh_task_execution_choices()
            app.task_execution_task.set(next(k for k,v in app.task_execution_map.items() if v==cancel_task))
            app.load_task_execution()
            app.task_execution_run_button.invoke()
            started = time.monotonic()
            while time.monotonic()-started < 4:
                root.update()
                if store.list_task_runs(cancel_task) and store.list_task_runs(cancel_task)[0]['status']=='running':
                    break
                time.sleep(.02)
            else:
                raise AssertionError('Cancel test did not reserve its subprocess')
            app.task_execution_cancel_button.invoke()
            started = time.monotonic()
            while app._task_runs_live and time.monotonic()-started < 6:
                root.update()
                time.sleep(.02)
            assert store.list_task_runs(cancel_task)[0]['status']=='cancelled', app.task_execution_feedback.get()
            assert store.read_task(cancel_task)['status']=='blocked'
            assert all(store.list_task_runs(t)[0]['status']=='success' for t in tasks)
            reopened = LocalStore(store.path)
            reopened.login('owner29','strong-password-stage29')
            assert all(reopened.list_task_runs(task)[0]['status']=='success' for task in tasks)
            assert all(reopened.read_task(task)['status']=='in_progress' for task in tasks)
            print('PASS Stage29 native Tk parallel two local CLI processes, distinct drafts, manual saves, SQLite restart')
        finally:
            messagebox.askyesno = old_confirm
            app.cancel_local_model(wait=True)
            root.destroy()


if __name__ == '__main__':
    main()
