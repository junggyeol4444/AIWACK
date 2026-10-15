"""Owner-visible AI company operations using existing employee/model/task/audit storage.

All work is real local model execution or explicitly labelled configuration data.
No fake agent messages, auto-sales, claimed earnings, unattended execution, or payments.
"""
from __future__ import annotations

import threading
from desktop.chief_runtime import invoke_chief_model
from desktop.task_runtime import invoke_task_execution
from desktop.stage87_90_management import stopped


def assert_running_allowed(store) -> None:
    store.require_permission('company:manage')
    with store._connect() as con:
        if stopped(con):
            raise PermissionError('비상 정지 상태입니다. 관리자 해제 전에는 AI 실행할 수 없습니다.')


def company_snapshot(store) -> dict:
    store.require_permission('company:manage')
    departments = store.list_departments()
    employees = store.list_employee_records()
    lines = {int(line['employee_id']):line for line in store.list_reporting_lines()}
    model_bindings = {int(row['employee_id']):row for row in store.list_employee_models()}
    tasks = store.list_tasks()
    artifacts = store.list_task_artifacts()
    chief = store.read_chief_profile()
    with store._connect() as con:
        emergency = stopped(con)
    dept = {int(row['id']):row['name'] for row in departments}
    team = [dict(id=int(e['id']), name=e['display_name'],
                 department=dept.get(e['department_id'], '미지정'),
                 tier=lines.get(int(e['id']),{}).get('tier','staff'),
                 model=(model_bindings.get(int(e['id']),{}).get('model_name') or '모델 미배정'),
                 lifecycle=e['lifecycle']) for e in employees]
    workload = []
    for task in tasks[:100]:
        assignment = store.read_task_routing(int(task['id']))
        workload.append(dict(id=int(task['id']), title=task['title'], status=task['status'],
                             assignee=assignment['employee_name'] or '담당자 미배정',
                             employee_id=assignment['employee_id'], priority=task.get('priority','normal')))
    return dict(company=store.read_company(), chief=chief, departments=departments, team=team,
                tasks=workload, total_tasks=len(tasks), artifacts=len(artifacts),
                completed=sum(t['status']=='done' for t in tasks),
                running=sum(t['status']=='in_progress' for t in tasks),
                emergency=emergency,
                live_model_ready=bool(chief and chief.get('model_id')),
                actual_sales_verified=False)


def create_task(store, title: str, description: str = '') -> int:
    """Add a genuine owner-approved task, not a fabricated AI-generated one."""
    store.require_permission('company:manage')
    if not isinstance(title,str) or not title.strip() or len(title)>120:
        raise ValueError('업무 제목은 1~120자여야 합니다.')
    if not isinstance(description,str) or len(description)>1500:
        raise ValueError('업무 설명은 1500자 이하여야 합니다.')
    return store.add_task(title.strip(),description.strip())


def assign_task(store, task_id: int) -> dict:
    assert_running_allowed(store)
    return store.auto_assign_task(task_id)


def execute_task(store, task_id: int, *, timeout: int=60,
                 cancel: threading.Event | None = None) -> dict:
    """Actually start the assigned staff member's configured local GGUF runner.

    Preserve the immutable run and artifact audits; do not mark finished before review.
    """
    assert_running_allowed(store)
    if cancel is not None and cancel.is_set():
        raise InterruptedError('시작 전 취소되었습니다.')
    # begin_task_execution additionally checks the same persisted stop under BEGIN IMMEDIATE.
    text = invoke_task_execution(store, task_id, timeout=timeout, cancel=cancel)
    runs = store.list_task_runs(task_id, limit=1)
    if not runs or runs[0]['status'] != 'success':
        raise RuntimeError('성공한 실제 직원 실행 감사 기록을 찾지 못했습니다.')
    if not text.strip():
        raise RuntimeError('모델이 빈 결과를 반환했습니다. 감사 기록은 보존했습니다.')
    task = store.read_task(task_id)
    artifact_id = store.save_task_artifact(task_id, int(runs[0]['id']),
                                           task['title'][:120], text[:20000])
    return {'task_id':task_id, 'run_id':runs[0]['id'], 'employee_id':runs[0]['employee_id'],
            'artifact_id':artifact_id,'response':text[:20000],
            'status':'awaiting_owner_review'}


def execute_batch(store, *, max_tasks: int=3, timeout: int=60,
                  cancel: threading.Event | None=None) -> list[dict]:
    """Explicitly triggered, bounded owner work session; not 24/7 autonomy."""
    if type(max_tasks) is not int or not 1<=max_tasks<=5:
        raise ValueError('한 번에 실행할 작업은 1~5개여야 합니다.')
    assert_running_allowed(store)
    results=[]
    for task in store.list_tasks():
        if len(results)>=max_tasks or (cancel is not None and cancel.is_set()):
            break
        if task['status']!='todo':
            continue
        tid=int(task['id'])
        try:
            assert_running_allowed(store)
            route=store.read_task_routing(tid)
            if not route['employee_id']:
                store.auto_assign_task(tid)
            response=execute_task(store,tid,timeout=timeout,cancel=cancel)
            results.append({'task_id':tid,'status':'draft_saved','artifact_id':response['artifact_id']})
        except (PermissionError,InterruptedError):
            raise
        except (ValueError,RuntimeError,OSError,TimeoutError) as exc:
            # Failure is visible; no fake completion and no silent retries.
            results.append({'task_id':tid,'status':'blocked','error':str(exc)[:400]})
    return results


def chief_brief(store, *, cancel: threading.Event | None=None) -> str:
    assert_running_allowed(store)
    snapshot=company_snapshot(store)
    prompt=('당신은 회사 총괄 AI입니다. 실제 확인된 정보만 사용하여 현재 부서와 업무의 '
            '우선순위 3개, 장애물, 다음에 사람에게 승인을 요청할 일에 대해 한국어로 답하세요. '
            '외부 실행·결제·수익 발생을 했다고 주장하지 마세요.\n'
            f"회사: {snapshot['company'].get('name','미설정')}\n"
            f"직원 정보: {len(snapshot['team'])}명, 부서: {len(snapshot['departments'])}개\n"
            f"업무: {snapshot['total_tasks']}건, 완료: {snapshot['completed']}건\n"
            '미완료 업무: '+', '.join(t['title'][:55] for t in snapshot['tasks']
                                    if t['status'] not in ('done','cancelled'))[:1200])
    return invoke_chief_model(store,prompt,timeout=60,cancel=cancel)
