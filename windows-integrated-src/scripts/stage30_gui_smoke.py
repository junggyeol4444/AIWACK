"""Real Tk buttons: chief draft -> owner approval -> worker -> artifact -> chief review."""
from pathlib import Path
import tempfile
import time
import tkinter as tk
from tkinter import messagebox

from desktop.app import AIWACKWindow
from desktop.model_runtime import ModelConfig
from desktop.storage import LocalStore


def await_ui(root, predicate, seconds=8):
    started=time.monotonic()
    while time.monotonic()-started<seconds:
        root.update()
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError('GUI wait timed out')


def main():
    with tempfile.TemporaryDirectory(prefix='aiwack-stage30-gui-') as folder:
        base=Path(folder)
        store=LocalStore(base/'stage30.sqlite3')
        root=tk.Tk()
        old=messagebox.askyesno
        try:
            app=AIWACKWindow(root,store)
            app.account_name.set('owner30')
            app.account_password.set('safe-local-gui-password30')
            app.password_confirm.set('safe-local-gui-password30')
            app.auth_button.invoke();root.update()
            assert store.is_authenticated
            runner=base/'local-runner'
            runner.write_text('#!/usr/bin/env python3\nprint("GUI30_LOCAL_RESULT")\n',encoding='utf-8')
            runner.chmod(0o700)
            gguf=base/'test.gguf';gguf.write_bytes(b'GGUF\x03\x00\x00\x00')
            model=store.add_local_model(ModelConfig('gui30 local','llama_cpp',str(runner),str(gguf),8))
            chief=store.add_employee_draft('gui30_chief','총괄 AI')
            worker=store.add_employee_draft('gui30_worker','직원 AI')
            store.assign_reporting_line(chief,'ceo')
            store.set_employee_model(chief,model)
            store.set_employee_model(worker,model)
            task=store.add_task('GUI30 handoff','GUI30 offline')
            assert store.auto_assign_task(task)['employee_id']==worker
            messagebox.askyesno=lambda *args,**kwargs:True
            app.tabs.select(19);root.update()
            app.refresh_chief_task_choices()
            app.chief_task_choice.set(next(k for k,v in app.chief_task_map.items() if v==task))
            app.load_chief_task()
            app.chief_task_objective.set('오프라인 보고서')
            app.chief_task_propose_button.invoke()
            await_ui(root,lambda:not app._model_running)
            assert 'GUI30_LOCAL_RESULT' in app.chief_task_instruction.get('1.0','end-1c'),app.chief_task_feedback.get()
            app.chief_task_approve_button.invoke()
            assert store.read_chief_task_order(task) is not None,app.chief_task_feedback.get()
            app.tabs.select(17);root.update()
            app.refresh_task_execution_choices()
            app.task_execution_task.set(next(k for k,v in app.task_execution_map.items() if v==task))
            app.load_task_execution()
            app.task_execution_run_button.invoke()
            await_ui(root,lambda:bool(store.list_task_runs(task)))
            await_ui(root,lambda:not app._task_runs_live)
            assert store.list_task_runs(task)[0]['status']=='success',app.task_execution_feedback.get()
            assert 'GUI30_LOCAL_RESULT' in app.task_execution_output.get('1.0','end-1c')
            app.save_current_task_draft()
            artifact=store.list_task_artifacts(task)[0]['id']
            app.tabs.select(19);root.update()
            app.refresh_chief_task_choices()
            app.chief_task_choice.set(next(k for k,v in app.chief_task_map.items() if v==task))
            app.load_chief_task()
            app.chief_task_artifact_choice.set(next(k for k,v in app.chief_task_artifact_map.items() if v==artifact))
            app.load_chief_task_report()
            app.chief_task_collect_button.invoke()
            await_ui(root,lambda:not app._model_running)
            assert 'GUI30_LOCAL_RESULT' in app.chief_task_report.get('1.0','end-1c'),app.chief_task_feedback.get()
            app.chief_task_save_report_button.invoke()
            report=store.find_chief_task_report(artifact)
            assert report and report['owner_decision']=='pending',app.chief_task_feedback.get()
            app.review_chief_task_report('accepted')
            assert store.find_chief_task_report(artifact)['owner_decision']=='accepted'
            assert store.read_task(task)['status']=='in_progress'
            store.logout()
            reopened=LocalStore(store.path)
            reopened.login('owner30','safe-local-gui-password30')
            assert reopened.find_chief_task_report(artifact)['owner_decision']=='accepted'
            print('PASS stage30 GUI chief->worker->artifact->chief report->owner review; offline persisted')
        finally:
            messagebox.askyesno=old
            root.destroy()


if __name__=='__main__':
    main()
