"""Real Korean Tk interaction, 31 AI role plan, actual SQLite saves; inference fixture only."""
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig
from desktop import company_operations as ops
from desktop import employee_model_runtime as model_runtime
from desktop import task_runtime, chief_task_runtime

with tempfile.TemporaryDirectory() as temp:
    root=tk.Tk()
    prior_confirm=messagebox.askyesno
    prior_model=model_runtime.run_local_model
    prior_task=task_runtime.run_local_model
    prior_review=chief_task_runtime.collect_chief_task_result
    try:
        store=LocalStore(Path(temp)/'campaign.sqlite3')
        ui=AIWACKWindow(root,store)
        ui.account_name.set('owner')
        ui.account_password.set('company-campaign-password-2026')
        ui.password_confirm.set('company-campaign-password-2026')
        ui.submit_setup()
        ops.initialize_company_blueprint(store)
        model=store.add_local_model(ModelConfig('fixture','llamafile',sys.executable,'',32))
        for employee in store.list_employee_records():
            store.set_employee_model(employee['id'],model)
        task=ops.create_task(store,'31명 15부서 회사 공동 사업 실행','소유자가 각 업무를 검수')
        def chief_result(config,prompt,**kwargs):
            names=prompt.rsplit('담당 부서: ',1)[1].split(', ')
            return '\n'.join(f'{n}|실제 계획|{n}의 역할과 결과물을 구체적으로 검수하세요' for n in names)
        model_runtime.run_local_model=chief_result
        task_runtime.run_local_model=lambda *args,**kwargs:'합성 테스트 직원 업무 결과물'
        chief_task_runtime.collect_chief_task_result=lambda *args,**kwargs:'합성 검수 의견'
        messagebox.askyesno=lambda *args,**kwargs:True
        for i in range(ui.tabs.index('end')):
            if ui.tabs.tab(i,'text')=='15부서·31명 실제 회사 협업':
                ui.tabs.select(i)
                break
        else:raise AssertionError('31 AI 회사 협업 GUI 탭 없음')
        root.update()
        assert ui.wide_propose_button.winfo_viewable()
        ui.wide_source.set(str(task))
        ui.wide_propose_button.invoke()
        deadline=time.monotonic()+14
        while time.monotonic()<deadline:
            root.update()
            if ui.wide_plan.get() and not ui._model_running:
                break
            time.sleep(.025)
        root.update()
        assert ui.wide_plan.get() and not ui._model_running, ui.wide_status.get()
        plan=int(ui.wide_plan.get())
        assert store.read_full_company_campaign(plan)['state']=='draft'
        assert len(store.list_tasks())==1
        ui._wide_approve()
        root.update()
        approved=store.read_full_company_campaign(plan)
        assert approved['state']=='approved'
        assert len({s['employee_id'] for s in approved['steps']})==30
        assert len({s['department'] for s in approved['steps']})==15
        assert len(store.list_tasks())==31
        ui.wide_execute_button.invoke()
        deadline=time.monotonic()+14
        while time.monotonic()<deadline:
            root.update()
            if not ui._model_running and '한 단계' in ui.wide_status.get():
                break
            time.sleep(.025)
        assert '한 단계' in ui.wide_status.get(),ui.wide_status.get()
        first=approved['steps'][0]
        artifacts=store.list_task_artifacts(first['task_id'])
        assert len(artifacts)==1
        assert artifacts[0]['review_status']=='pending'
        root.destroy()
        store.logout()
        reloaded=LocalStore(store.path)
        reloaded.login('owner','company-campaign-password-2026')
        after=reloaded.read_full_company_campaign(plan)
        assert after['state']=='approved' and len(after['steps'])==30
        print('NATIVE_TK_WIDE_15_DEPARTMENT_31_ROLE_CAMPAIGN_GUI_PASS')
        print('NATIVE_TK_CAMPAIGN_MODEL_RESPONSES_ARE_SYNTHETIC_FIXTURES')
    finally:
        model_runtime.run_local_model=prior_model
        task_runtime.run_local_model=prior_task
        chief_task_runtime.collect_chief_task_result=prior_review
        messagebox.askyesno=prior_confirm
        try:
            if root.winfo_exists():root.destroy()
        except tk.TclError:pass
