"""Owner desktop mouse scenario with real chief and staff subprocess invocations.

The runner is a deliberately synthetic executable, NOT GGUF intelligence.
The true Tk UI buttons are physically clicked from mouse/keyboard; task audits
must show chief draft, explicit owner consent, employee execution and review.
"""
from __future__ import annotations

import os
import sys
import json
import tempfile
import time
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import pyautogui

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig
from desktop import company_operations as office_ops


def find_button(widget,label):
    for child in widget.winfo_children():
        if isinstance(child,tk.Button) and child.cget('text')==label:
            return child
        b=find_button(child,label)
        if b is not None:return b
    return None


def toplevels(widget):
    result=[]
    for child in widget.winfo_children():
        if isinstance(child,tk.Toplevel):result.append(child)
        result.extend(toplevels(child))
    return result


def click(widget):
    assert widget is not None and widget.winfo_viewable(), f'Button not visible: {widget}'
    pyautogui.click(widget.winfo_rootx()+widget.winfo_width()//2,
                    widget.winfo_rooty()+widget.winfo_height()//2)


def wait_for(root,predicate,timeout=50):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        root.update()
        obj=predicate()
        if obj:return obj
        time.sleep(.12)
    raise AssertionError('Visible real-AI UI flow did not reach expected state in time')


def click_task_row(root,office,task_id):
    office.set_view('work')
    office.refresh()
    root.update()
    rect=office.work_jobs.bbox(str(task_id))
    assert rect and office.work_jobs.winfo_viewable(), 'Worker task not visible on board'
    pyautogui.click(office.work_jobs.winfo_rootx()+rect[0]+max(12,rect[2]//3),
                    office.work_jobs.winfo_rooty()+rect[1]+rect[3]//2)
    root.update()
    assert int(office.work_jobs.selection()[0])==task_id


def fill_prompt(root):
    # This Tk callback runs inside simpledialog's nested event loop after the
    # user's click, so keyboard input is sent to the real visible dialog.
    def find_input(widget):
        for child in widget.winfo_children():
            if isinstance(child,tk.Entry) and child.winfo_viewable():return child
            item=find_input(child)
            if item:return item
        return None
    dialogs=[w for w in root.winfo_children() if isinstance(w,tk.Toplevel)
             and w.winfo_exists() and w.winfo_viewable()]
    visible=next((find_input(d) for d in dialogs if find_input(d) is not None),None)
    if visible is None:
        # Windows may need longer than 350 ms to construct the native dialog.
        # Retry finding the *visible* entry; never write to a hidden widget.
        root.after(180,lambda:fill_prompt(root))
        return
    click(visible)
    pyautogui.write('Investigate the local market safely',.007)
    def confirm_user_dialog():
        # Physically click the Windows/Tk OK button; Return alone may be
        # consumed by the entry or another focused Windows control.
        ok=find_button(visible.winfo_toplevel(),'OK')
        if ok is not None and ok.winfo_viewable():
            click(ok)
        else:
            pyautogui.press('enter')
    root.after(550,confirm_user_dialog)



def screenshot_if_requested(stage):
    original=os.environ.get('AIWACK_CHIEF_LIVE_SCREENSHOT')
    if not original:
        return
    output=Path(original)
    output.parent.mkdir(parents=True,exist_ok=True)
    destination=output.with_name(output.stem+'-'+stage+output.suffix)
    pyautogui.screenshot().save(destination)


def main():
    pyautogui.PAUSE=.1
    with tempfile.TemporaryDirectory(prefix='aiwack-real-chief-flow-') as directory:
        path=Path(directory)
        runner_env=os.environ.get('AIWACK_NATIVE_SYNTHETIC_RUNNER','')
        if runner_env:
            runner=Path(runner_env).resolve()
            assert runner.is_file() and runner.suffix.lower()=='.exe'
            config=ModelConfig('WINDOWS native synthetic test','llamafile',str(runner),'',24)
        else:
            if os.name=='nt':
                raise AssertionError('Windows UI subprocess test requires a real native Windows synthetic .exe')
            runner=path/'native-synthetic-runner'
            runner.write_text('#!/usr/bin/env python3\nimport sys\nprint("AIWACK_NATIVE_CLI_TEST", " ".join(sys.argv[1:])[:100])\n',encoding='utf-8')
            runner.chmod(0o700)
            gguf=path/'synthetic.gguf';gguf.write_bytes(b'GGUF\x03\x00\x00\x00')
            config=ModelConfig('POSIX native synthetic test','llama_cpp',str(runner),str(gguf),24)
        store=LocalStore(path/'office.sqlite3')
        store.setup_owner('real_flow_owner','owner-flow-password-2026')
        chief=store.add_employee_draft('real_chief','총괄 AI')
        worker=store.add_employee_draft('real_worker','직원 AI')
        store.assign_reporting_line(chief,'ceo')
        model=store.add_local_model(config)
        store.set_employee_model(chief,model)
        store.set_employee_model(worker,model)
        task=office_ops.create_task(store,'시장 조사 실제 프로세스 검사','합성 실행 파일로 경로 검증만 수행')
        assert office_ops.assign_task(store,task)['employee_id']==worker
        root=tk.Tk()
        try:
            root.geometry('1040x720+20+20')
            app=AIWACKWindow(root,store)
            app.account_name.set('real_flow_owner')
            app.account_password.set('owner-flow-password-2026')
            app.submit_login()
            office=app.company_office
            click_task_row(root,office,task)
            root.after(650,lambda:fill_prompt(root))
            click(find_button(office.views['work'],'총괄 AI 지시 초안'))
            try:
                wait_for(root,lambda:next((w for w in toplevels(root)
                  if w.winfo_exists() and '총괄 AI 지시 초안' in w.title()),None),timeout=55)
            except AssertionError:
                dest=os.environ.get('AIWACK_CHIEF_LIVE_SCREENSHOT')
                if dest:
                    failure=Path(dest).with_name('chief-staff-native-subprocess-failure.png')
                    failure.parent.mkdir(parents=True,exist_ok=True)
                    pyautogui.screenshot().save(failure)
                # GitHub Windows Python stdout can be CP1252. Use safe ASCII
                # JSON so the *real* failure is not replaced by UnicodeError.
                details={'status':office.status.get(),
                         'dialogs':[(w.title(),w.winfo_geometry()) for w in toplevels(root)],
                         'chief_model_calls':len(store.list_employee_model_calls(chief))}
                print('REAL_GUI_CHIEF_ORDER_FAILURE',
                      json.dumps(details,ensure_ascii=True),flush=True)
                raise
            dialog=next(w for w in toplevels(root)
              if '총괄 AI 지시 초안' in w.title())
            assert store.read_chief_task_order(task) is None
            assert store.list_task_runs(task)==[]
            if os.environ.get('AIWACK_CHIEF_LIVE_SCREENSHOT'):
                dst=Path(os.environ['AIWACK_CHIEF_LIVE_SCREENSHOT'])
                dst.parent.mkdir(parents=True,exist_ok=True)
                pyautogui.screenshot().save(dst)
            click(find_button(dialog,'확인 후 지시 승인'))
            root.update()
            assert store.read_chief_task_order(task) is not None
            assert store.list_task_runs(task)==[]
            click_task_row(root,office,task)
            click(find_button(office.views['work'],'선택 업무 실행'))
            artifact=wait_for(root,lambda:next(iter(store.list_task_artifacts(task)),None),timeout=40)
            assert 'NATIVE_CLI' in store.read_task_artifact(artifact['id'])['body'] or 'AIWACK_WINDOWS_NATIVE_CLI' in store.read_task_artifact(artifact['id'])['body']
            assert store.read_task(task)['status']=='in_progress'
            assert len(store.list_employee_model_calls(chief))==1
            assert len(store.list_employee_model_calls(worker))==1
            assert store.read_task_artifact(artifact['id'])['review_status']=='pending'
            print('REAL_GUI_CHIEF_ASK_OWNER_APPROVE_WORKER_EXECUTE_AUDIT_PASS',flush=True)
            # Physically use the result review queue after real subprocess calls.
            office.set_view('results')
            office.refresh()
            root.update()
            office.artifact_list.selection_set(str(artifact['id']))
            office.artifact_list.see(str(artifact['id']))
            root.update()
            assert int(office.artifact_list.selection()[0]) == artifact['id']

            def click_and_confirm(widget):
                # Schedule Return while Tk's native confirmation dialog owns
                # its nested event loop, instead of bypassing owner approval.
                root.after(500, lambda: pyautogui.press('enter'))
                click(widget)
                root.update()

            click_and_confirm(find_button(office.views['results'], '총괄 AI 회수 검토'))
            report=wait_for(root,lambda:store.find_chief_task_report(artifact['id']),timeout=50)
            assert report['owner_decision']=='pending'
            assert store.read_task_artifact(artifact['id'])['review_status']=='pending'
            assert store.read_task(task)['status']=='in_progress'
            assert len(store.list_employee_model_calls(chief))==2
            report_dialog=wait_for(root,lambda:next((w for w in toplevels(root)
                    if w.winfo_exists() and '총괄 AI 회수 보고서' in w.title()),None),timeout=20)
            screenshot_if_requested('report-owner-decision-visible')
            click_and_confirm(find_button(report_dialog,'총괄 보고서 수락'))
            def accepted_report():
                found=store.find_chief_task_report(artifact['id'])
                return found if found and found['owner_decision']=='accepted' else None
            report=wait_for(root,accepted_report,timeout=30)
            assert report['owner_decision']=='accepted'
            assert store.read_task_artifact(artifact['id'])['review_status']=='pending'
            assert store.read_task(task)['status']=='in_progress'
            screenshot_if_requested('chief-report-accepted-task-not-done')

            office.set_view('results')
            office.refresh()
            root.update()
            office.artifact_list.selection_set(str(artifact['id']))
            click_and_confirm(find_button(office.views['results'],'승인'))
            assert store.read_task_artifact(artifact['id'])['review_status']=='approved'
            assert store.read_task(task)['status']=='in_progress'
            office.artifact_list.selection_set(str(artifact['id']))
            click_and_confirm(find_button(office.views['results'],'승인 결과로 업무 완료'))
            assert store.read_task(task)['status']=='done'
            screenshot_if_requested('owner-approved-task-done')

            store.logout()
            reopened=LocalStore(store.path)
            reopened.login('real_flow_owner','owner-flow-password-2026')
            assert reopened.read_task(task)['status']=='done'
            assert reopened.read_chief_task_order(task) is not None
            assert reopened.find_chief_task_report(artifact['id'])['owner_decision']=='accepted'
            assert reopened.read_task_artifact(artifact['id'])['review_status']=='approved'
            assert len(reopened.list_employee_model_calls(chief))==2
            assert len(reopened.list_employee_model_calls(worker))==1
            assert office_ops.company_snapshot(reopened)['actual_sales_verified'] is False
            print('PHYSICAL_TK_CHIEF_STAFF_REVIEW_FINALIZE_SQLITE_REOPEN_PASS '
                  '(synthetic subprocess; not a packaged EXE or GGUF model)',flush=True)
        finally:
            root.destroy()

if __name__=='__main__':main()
