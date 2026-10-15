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
                open_tasks=sum(t['status'] not in ('done','cancelled') for t in tasks),
                completed=sum(t['status']=='done' for t in tasks),
                running=sum(t['status']=='in_progress' for t in tasks),
                emergency=emergency,
                model_ready_count=sum(bool(model_bindings.get(int(e['id']),{}).get('model_name'))
                                      for e in employees),
                pending_reviews=sum(a['review_status']=='pending' for a in artifacts),
                recent_artifacts=artifacts[:75],
                live_model_ready=bool(chief and chief.get('model_id')),
                actual_sales_verified=False)



# Original specification chapter 2.3: fifteen functional departments.
BLUEPRINT_DEPARTMENTS = (
    ('경영기획부','사업 전략, 회사 목표와 운영 계획'),
    ('시장조사부','시장 조사, 경쟁사 및 수요 분석'),
    ('연구개발부','기술 조사, 개발과 테스트'),
    ('상품기획부','상품 기획과 가격 설계'),
    ('콘텐츠제작부','글, 영상 및 문서 제작'),
    ('디자인부','UI, UX와 그래픽'),
    ('마케팅부','홍보 및 유입 분석'),
    ('영업부','제안과 고객 발굴'),
    ('고객지원부','문의와 사후 지원'),
    ('재무회계부','매출, 예산 및 비용 검토'),
    ('법무관리부','계약 및 약관 검토 지원'),
    ('인사관리부','직원 및 조직 관리'),
    ('품질관리부','결과물 오류 및 품질 검수'),
    ('운영관리부','일정, 서비스 및 장애 대응'),
    ('데이터분석부','데이터 분석과 성과 예측'),
)


def initialize_company_blueprint(store) -> dict:
    """User-clicked 15 departments + 31 non-executing draft AI profiles.

    A blueprint is NOT 31 running LLMs; each model requires separate assignment.
    Fail rather than overwriting existing organization records. The program
    creates data only after the owner clicks the confirmation button.
    """
    store.require_permission('agents:manage')
    if store.list_departments() or store.list_employee_records():
        raise ValueError('이미 조직이 존재합니다. 기존 부서와 직원을 보존하기 위해 초기 구성을 거부합니다.')
    dept_ids=[store.add_department(name,description) for name,description in BLUEPRINT_DEPARTMENTS]
    chief=store.add_employee_draft('office_chief','총괄 AI (모델 미배정)',
                                   '전체 회사 운영과 의사결정')
    store.assign_reporting_line(chief,'ceo')
    for index, ((name,description),did) in enumerate(zip(BLUEPRINT_DEPARTMENTS,dept_ids),1):
        manager=store.add_employee_draft(f'office_d{index:02d}_head',f'{name} 부서장 AI',
            description,department_id=did)
        store.assign_reporting_line(manager,'department_head',chief)
        staff=store.add_employee_draft(f'office_d{index:02d}_staff',f'{name} 직원 AI',
            description,department_id=did)
        store.assign_reporting_line(staff,'staff',manager)
    return {'departments':len(dept_ids),'draft_ai_profiles':31,
            'chief_employee_id':chief,'real_model_calls':0}


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
