"""Owner-visible AI company operations using existing employee/model/task/audit storage.

All work is real local model execution or explicitly labelled configuration data.
No fake agent messages, auto-sales, claimed earnings, unattended execution, or payments.
"""
from __future__ import annotations

import threading
import json
import re
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
    proposal_rows = store.list_autonomous_task_proposals(limit=100)
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
                pending_proposals=sum(row['status']=='pending' for row in proposal_rows),
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
    if cancel is not None and cancel.is_set():
        raise InterruptedError('소유자 취소 후 직원 결과물을 저장하지 않습니다.')
    assert_running_allowed(store)
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



def execute_approved_chief_cycle(store, task_id: int, *,
                                 cancel: threading.Event | None = None) -> dict:
    """Run staff then chief-review automatically AFTER a human-approved order.

    One explicitly approved task; never schedule jobs, retry a failed model,
    accept the chief report, approve artifacts, or finalize tasks. Each model
    call goes through the existing subprocess/audit, timeout and stop guards.
    """
    assert_running_allowed(store)
    if type(task_id) is not int or task_id <= 0:
        raise ValueError('자동 실행할 업무 번호가 올바르지 않습니다.')
    if cancel is not None and cancel.is_set():
        raise InterruptedError('자동 실행 시작 전에 관리자가 취소했습니다.')
    order = store.read_chief_task_order(task_id)
    if order is None:
        raise ValueError('소유자가 승인한 총괄 AI 지시가 필요합니다.')
    task = store.read_task(task_id)
    if task['status'] != 'todo':
        raise ValueError('아직 실행하지 않은 업무만 1회 자동 실행할 수 있습니다.')
    if store.list_task_runs(task_id) or store.list_task_artifacts(task_id):
        raise ValueError('기존 실행 기록이 있어 중복 자동 실행하지 않습니다.')
    routing = store.read_task_routing(task_id)
    if not routing['employee_id']:
        raise ValueError('업무에 담당 직원을 먼저 배정하세요.')
    if store.read_employee_model(int(routing['employee_id'])) is None:
        raise ValueError('담당 직원의 로컬 AI 모델을 먼저 연결하세요.')
    worker = execute_task(store, task_id, cancel=cancel)
    # Cancellation leaves the draft for human recovery but never starts
    # a late chief-model call or approves a result.
    if cancel is not None and cancel.is_set():
        raise InterruptedError('직원 결과를 저장했으나 관리자가 취소해 총괄 검토는 중단했습니다.')
    assert_running_allowed(store)
    report = collect_chief_review(store, int(worker['artifact_id']), cancel=cancel)
    return {**report, 'task_id':task_id, 'run_id':worker['run_id'],
            'worker_employee_id':worker['employee_id'],
            'automatic_worker_and_chief': True,
            'owner_approval_required': True}



def list_approved_chief_queue_candidates(store, *, limit: int = 3) -> list[dict]:
    """Read-only preview of exactly the approved, model-ready company tasks.

    No model invocation, dispatch, approval or database modification here.
    The executor revalidates every owner-confirmed ID before running a task.
    """
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 3:
        raise ValueError('한 번에 자동 실행 가능한 승인 업무는 1~3건입니다.')
    candidates = []
    for task in sorted(store.list_tasks(), key=lambda t: int(t['id'])):
        task_id = int(task['id'])
        if task['status'] != 'todo' or store.read_chief_task_order(task_id) is None:
            continue
        if store.list_task_runs(task_id) or store.list_task_artifacts(task_id):
            continue
        # An approved chief instruction is NOT permission to run a task
        # while its prerequisites are still unfinished.
        with store._connect() as con:
            if store._pending_prerequisites(con,task_id):
                continue
        route = store.read_task_routing(task_id)
        employee_id = route['employee_id']
        if not employee_id or store.read_employee_model(int(employee_id)) is None:
            continue
        candidates.append({'task_id': task_id, 'title': task['title'],
                           'employee_id': int(employee_id)})
        if len(candidates) >= limit:
            break
    return candidates


def execute_approved_chief_queue(store, *, limit: int = 3,
                                 cancel: threading.Event | None = None,
                                 expected_task_ids: tuple[int, ...] | None = None) -> dict:
    """Run up to three EXISTING owner-approved tasks sequentially.

    No implicit chief order approval, no model discovery, no payments,
    no retries on failure, no automatic result acceptance or task completion.
    The task snapshot is bounded; new tasks require a future owner action.
    """
    assert_running_allowed(store)
    if type(limit) is not int or not 1 <= limit <= 3:
        raise ValueError('한 번에 자동 실행 가능한 승인 업무는 1~3건입니다.')
    if cancel is not None and cancel.is_set():
        raise InterruptedError('승인 업무 자동 실행 전에 취소됐습니다.')
    if expected_task_ids is not None:
        if (type(expected_task_ids) is not tuple or not expected_task_ids
                or len(expected_task_ids) > limit
                or any(type(tid) is not int or tid <= 0 for tid in expected_task_ids)
                or len(set(expected_task_ids)) != len(expected_task_ids)):
            raise ValueError('소유자가 확인한 승인 업무 번호 목록이 올바르지 않습니다.')
    candidates = list_approved_chief_queue_candidates(store, limit=limit)
    selected = tuple(item['task_id'] for item in candidates)
    if not selected:
        raise ValueError('실행 가능한 소유자 승인·직원 모델 연결 업무가 없습니다.')
    if expected_task_ids is not None and selected != expected_task_ids:
        raise ValueError('확인한 승인 업무 목록이 변경됐습니다. 다시 확인하고 승인하세요.')
    reports=[]
    for index, tid in enumerate(selected):
        if cancel is not None and cancel.is_set():
            raise InterruptedError('대기열 진행 도중 관리자가 취소했습니다.')
        assert_running_allowed(store)
        # Re-check before EVERY subprocess. Never replace a confirmed task
        # with one added by another UI session during an earlier execution.
        remaining = tuple(item['task_id'] for item in
            list_approved_chief_queue_candidates(store, limit=len(selected)-index))
        if remaining != selected[index:]:
            raise ValueError('승인 업무가 대기열 실행 중 변경됐습니다. 다음 업무를 시작하지 않습니다.')
        reports.append(execute_approved_chief_cycle(store,tid,cancel=cancel))
    return {'reports':reports,'task_ids':list(selected),
            'completed_cycles':len(reports),
            'pending_owner_review':len(reports),
            'auto_approved':False,'tasks_finalized':False}


def list_approved_parallel_candidates(store) -> list[dict]:
    """Owner-visible read-only preview of two independent, approved AI staff tasks.

    The two workers must be distinct. Model connectivity and approved orders
    are required. The task reservation transaction checks dependencies again.
    """
    store.require_permission('company:manage')
    candidates = []
    chosen_staff = set()
    for task in sorted(store.list_tasks(), key=lambda row: int(row['id'])):
        task_id = int(task['id'])
        if task['status'] != 'todo' or store.read_chief_task_order(task_id) is None:
            continue
        if store.list_task_runs(task_id) or store.list_task_artifacts(task_id):
            continue
        # Skip blocked dependency chains in the read-only preview as well.
        # The SQL run reservation separately checks prerequisites again.
        with store._connect() as con:
            if store._pending_prerequisites(con, task_id):
                continue
        route = store.read_task_routing(task_id)
        staff = route['employee_id']
        if not staff or int(staff) in chosen_staff or store.read_employee_model(int(staff)) is None:
            continue
        candidates.append({'task_id': task_id, 'title': task['title'], 'employee_id': int(staff)})
        chosen_staff.add(int(staff))
        if len(candidates) == 2:
            break
    return candidates


def execute_approved_parallel_cycle(store, *, expected_task_ids: tuple[int, int],
                                    expected_employee_ids: tuple[int, int],
                                    cancel: threading.Event | None = None) -> dict:
    """Run TWO owner-confirmed, different employees concurrently, then chief reviews.

    A failure/cancellation stops the remaining model promptly and keeps all
    individual SQL audit trails. Partial worker artifacts remain pending for
    owner inspection, never automatically approved or repeated. No external
    tool execution, billing or automatic completion occurs here.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    assert_running_allowed(store)
    if (type(expected_task_ids) is not tuple or len(expected_task_ids) != 2
            or any(type(tid) is not int or tid <= 0 for tid in expected_task_ids)
            or len(set(expected_task_ids)) != 2):
        raise ValueError('소유자가 확인한 서로 다른 승인 업무 번호 2개가 필요합니다.')
    if (type(expected_employee_ids) is not tuple or len(expected_employee_ids) != 2
            or any(type(employee_id) is not int or employee_id <= 0
                   for employee_id in expected_employee_ids)
            or len(set(expected_employee_ids)) != 2):
        raise ValueError('소유자가 확인한 서로 다른 담당 직원 AI 번호 2개가 필요합니다.')
    if cancel is not None and cancel.is_set():
        raise InterruptedError('직원 병렬 업무 실행 전에 관리자가 취소했습니다.')
    preview = list_approved_parallel_candidates(store)
    if (tuple(row['task_id'] for row in preview) != expected_task_ids
            or tuple(row['employee_id'] for row in preview) != expected_employee_ids):
        raise ValueError('병렬 업무 대상 또는 담당 직원이 변경됐습니다. 다시 확인하세요.')
    # Shared stop signal is passed to both real local subprocess runners.
    # The caller's event remains the single cancellation point for its GUI.
    shared_cancel = cancel if cancel is not None else threading.Event()
    workers: dict[int, dict] = {}
    errors: dict[int, Exception] = {}
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix='AIWACK-approved-staff') as pool:
        tasks = {pool.submit(execute_task, store, tid, cancel=shared_cancel): tid
                 for tid in expected_task_ids}
        for future in as_completed(tasks):
            tid = tasks[future]
            try:
                workers[tid] = future.result()
            except Exception as exc:
                errors[tid] = exc
                shared_cancel.set()
    if errors:
        # Report the owner emergency stop deterministically even if a peer
        # happened to record a cancellation first in task-ID order.
        first = next((err for err in errors.values() if isinstance(err, PermissionError)), None)
        if first is None:
            first = next(errors[t] for t in expected_task_ids if t in errors)
        # Preserve the exact original error type and all saved run audits.
        raise type(first)('병렬 업무 일부가 실패하여 후속 총괄 AI를 실행하지 않았습니다. '
                          f'실패 업무: {sorted(errors)} · {str(first)[:250]}')
    if shared_cancel.is_set():
        raise InterruptedError('병렬 실행 종료 후 관리자가 취소하여 총괄 검토를 시작하지 않습니다.')
    # Both staff results were durably saved. Chief calls are intentionally
    # serialized because the same chief model cannot serve two at once.
    reports = []
    for task_id in expected_task_ids:
        assert_running_allowed(store)
        if shared_cancel.is_set():
            raise InterruptedError('총괄 검토 중 취소되었습니다. 저장된 직원 결과는 보존됩니다.')
        reports.append(collect_chief_review(store, int(workers[task_id]['artifact_id']),
                                            cancel=shared_cancel))
    return {'task_ids': list(expected_task_ids),
            'staff_execution_parallel': True, 'staff_executions': 2,
            'chief_reviews': 2, 'reports': reports,
            'pending_owner_review': 2, 'auto_approved': False,
            'tasks_finalized': False}


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


# Owner-visible planning workflow. The existing SQL draft store is authoritative.
# The scan is rule-based; only refine_planning_proposal calls the actual chief model.
def planning_proposals(store, *, limit: int=60) -> list[dict]:
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('제안 조회는 1~100개입니다.')
    proposals = store.list_autonomous_task_proposals(limit=limit)
    assessments = {int(item['proposal_id']):item
                   for item in store.list_task_proposal_assessments(limit=200)}
    return [{**row, 'analysis':assessments.get(int(row['id']))}
            for row in proposals]


def scan_planning_proposals(store) -> dict:
    """Deterministic local drafting only, not autonomous model execution."""
    store.require_permission('company:manage')
    return store.scan_autonomous_task_proposals(limit=30)


def _parse_chief_proposal(text: str) -> tuple[str,str]:
    """Strictly parse inert JSON text returned by the configured LLM."""
    if not isinstance(text,str) or len(text)>12000:
        raise ValueError('총괄 AI 응답이 없거나 허용 크기를 넘었습니다.')
    payload=text.strip()
    match=re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', payload, flags=re.S|re.I)
    if match:
        payload=match.group(1)
    try:
        result=json.loads(payload)
    except (TypeError,ValueError) as exc:
        raise ValueError('총괄 AI 응답이 JSON 형식이 아닙니다. 제안은 저장하지 않았습니다.') from exc
    if type(result) is not dict or set(result)!={'title','description'}:
        raise ValueError('총괄 AI는 제목과 설명만 제안할 수 있습니다.')
    title,detail=result['title'],result['description']
    if type(title) is not str or not 1<=len(title.strip())<=120:
        raise ValueError('제안 제목 길이가 잘못됐습니다.')
    if type(detail) is not str or not 1<=len(detail.strip())<=1500:
        raise ValueError('제안 설명 길이가 잘못됐습니다.')
    return title.strip(),detail.strip()


def refine_planning_proposal(store, proposal_id: int, *, cancel: threading.Event|None=None) -> dict:
    """Actually call configured chief LLM once, but save ONLY an inert draft.

    The owner still needs to approve the proposal to create a real task.
    No tool execution, payments, completion or fake model output.
    """
    assert_running_allowed(store)
    if type(proposal_id) is not int or proposal_id<=0:
        raise ValueError('제안 ID가 올바르지 않습니다.')
    candidates=planning_proposals(store,limit=100)
    row=next((x for x in candidates if x['id']==proposal_id),None)
    if row is None or row['status']!='pending' or row['origin']!='rule':
        raise ValueError('대기 중인 규칙 기반 제안만 한 번 구체화할 수 있습니다.')
    prompt=('당신은 실제 로컬 모델로 실행되는 총괄 AI입니다. 다음 회사 업무의 위험과 구체적 다음 행동을 '
            '정리하십시오. 실행·외부 전송·결제는 절대 하지 말고 JSON 객체 하나만 출력하십시오. '
            'JSON 키는 title, description 두 개이고 값은 한국어 문자열입니다. '
            'title은 120자 이하, description은 1500자 이하로 작성하십시오. '
            '허위 시장 수요·매출·완료·모델 실행 결과를 주장하지 마십시오.\n'
            f"원본 제안 #{proposal_id}: {row['title'][:120]}\n"
            f"원본 설명: {row['description'][:600]}")
    response=invoke_chief_model(store,prompt,timeout=60,cancel=cancel)
    if cancel is not None and cancel.is_set():
        raise InterruptedError('총괄 AI 제안 수신 뒤 관리자가 취소했습니다.')
    title,detail=_parse_chief_proposal(response)
    # Storage performs final atomic source-eligibility and owner-session checks.
    if not store.save_local_ai_task_proposal(proposal_id,title,detail):
        raise ValueError('원본 목표/업무가 변경되어 제안을 폐기했습니다.')
    return {'proposal_id':proposal_id,'title':title,'description':detail,
            'state':'awaiting_owner_approval','chief_model_called':True,'task_created':False}


def approve_planning_proposal(store, proposal_id: int) -> int|None:
    store.require_permission('company:manage')
    return store.approve_autonomous_task_proposal(proposal_id)


def reject_planning_proposal(store, proposal_id: int) -> None:
    store.require_permission('company:manage')
    store.reject_autonomous_task_proposal(proposal_id)


def create_active_company_goal(store, title: str) -> int:
    """Explicit owner-created active goal, not an AI-decided business action.

    Enables the next planning-screen scan without navigating legacy forms.
    Each write uses the existing company-goal SQLite validation and audit paths.
    """
    store.require_permission('company:manage')
    if type(title) is not str or not 1<=len(title.strip())<=120:
        raise ValueError('회사 목표 제목은 1~120자여야 합니다.')
    goal=store.add_goal(title.strip())
    store.update_goal(goal,title.strip(),'','active')
    return goal


def draft_chief_order(store, task_id: int, objective: str,
                      *, cancel: threading.Event | None = None) -> dict:
    """Real chief-model suggestion, still inert until owner explicitly approves.

    The existing owner-authenticated chief runtime enforces a configured CEO,
    while the storage API prevents a stale/duplicate instruction dispatch.
    """
    from desktop.chief_task_runtime import propose_chief_task_order
    assert_running_allowed(store)
    if type(task_id) is not int or task_id <= 0:
        raise ValueError('업무 번호가 올바르지 않습니다.')
    if type(objective) is not str or not 1 <= len(objective.strip()) <= 500 or '\x00' in objective:
        raise ValueError('총괄 AI 업무 목표를 1~500자로 입력하세요.')
    if cancel is not None and cancel.is_set():
        raise InterruptedError('총괄 AI 호출 전에 취소되었습니다.')
    reply=propose_chief_task_order(store,task_id,objective.strip(),timeout=60,cancel=cancel)
    if cancel is not None and cancel.is_set():
        raise InterruptedError('취소된 지시 초안은 폐기합니다.')
    if type(reply) is not str or not 1 <= len(reply.strip()) <= 600 or '\x00' in reply:
        raise ValueError('총괄 AI 지시는 1~600자의 검토 가능한 텍스트여야 합니다.')
    return {'task_id':task_id,'instruction':reply.strip(),
            'chief_model_called':True,'owner_approved':False,
            'worker_executed':False}


def approve_chief_order(store, task_id: int, instruction: str) -> int:
    """Human-only approval before any worker can execute the chief's instruction."""
    assert_running_allowed(store)
    return store.approve_chief_task_order(task_id,instruction)


def collect_chief_review(store, artifact_id: int, *,
                         cancel: threading.Event | None = None) -> dict:
    """Call the real configured chief model for an already saved employee result.

    Only results executed from owner-approved chief orders qualify. The result
    is an auditable *pending* chief report. Never accept the report, approve the
    staff artifact, mark the task done, or perform external side effects.
    """
    from desktop.chief_task_runtime import collect_chief_task_result
    assert_running_allowed(store)
    if type(artifact_id) is not int or artifact_id <= 0:
        raise ValueError('검토할 결과물 번호가 올바르지 않습니다.')
    if cancel is not None and cancel.is_set():
        raise InterruptedError('총괄 AI 회수 검토 시작 전에 취소됐습니다.')
    if store.find_chief_task_report(artifact_id) is not None:
        raise ValueError('이미 회수 보고서가 저장된 결과물입니다.')
    # A durable BEGIN IMMEDIATE lease excludes a second Windows session from
    # starting the same expensive chief subprocess before the report is saved.
    from desktop import company_chief_review_leases as review_leases
    lease_token = review_leases.reserve(store, artifact_id)
    try:
        # The core runtime verifies provenance, chief assignment, full text size
        # and owner permission BEFORE constructing the model prompt.
        response = collect_chief_task_result(store, artifact_id, timeout=60, cancel=cancel)
        if cancel is not None and cancel.is_set():
            raise InterruptedError('회수 검토 도중 취소되어 AI 응답을 저장하지 않았습니다.')
        assert_running_allowed(store)
        if type(response) is not str or not response.strip() or len(response) > 10000 or '\x00' in response:
            raise ValueError('총괄 AI 회수 의견이 비었거나 저장 제한을 초과했습니다.')
        report_id = store.save_chief_task_report(artifact_id, response.strip(), lease_token=lease_token)
        return {'artifact_id': artifact_id, 'report_id': report_id,
                'status': 'awaiting_owner_review', 'chief_model_called': True,
                'worker_result_auto_approved': False, 'task_completed': False}
    finally:
        review_leases.release(store, artifact_id, lease_token)



def recover_interrupted_chief_review(store, task_id: int, *,
                                     cancel: threading.Event | None = None) -> dict:
    """Owner-triggered T17 recovery of a SAVED worker result after interruption.

    A crash or emergency stop after a successful worker run must not rerun the
    worker or silently approve anything. Use the single existing audited
    artifact for an already approved task, and execute ONLY the missing chief
    review after the owner explicitly requests recovery in the native GUI.
    """
    assert_running_allowed(store)
    if type(task_id) is not int or task_id <= 0:
        raise ValueError('복구할 업무 번호가 올바르지 않습니다.')
    if cancel is not None and cancel.is_set():
        raise InterruptedError('중단된 검토 복구 전에 관리자가 취소했습니다.')
    task = store.read_task(task_id)
    if task['status'] != 'in_progress':
        raise ValueError('실행 중 중단되어 저장된 업무만 검토를 재개할 수 있습니다.')
    if store.read_chief_task_order(task_id) is None:
        raise ValueError('관리자가 승인한 총괄 AI 지시가 없습니다.')
    artifacts = store.list_task_artifacts(task_id)
    if len(artifacts) != 1 or artifacts[0]['review_status'] != 'pending':
        raise ValueError('복구 가능한 단일 미검수 결과물이 필요합니다.')
    artifact_id = int(artifacts[0]['id'])
    # Confirm provenance against the real signed-off chief dispatch and
    # successful stored employee run before starting any new model subprocess.
    context = store.chief_task_report_context(artifact_id)
    if int(context['task_id']) != task_id:
        raise ValueError('업무와 승인 결과물의 연결이 일치하지 않습니다.')
    if store.find_chief_task_report(artifact_id) is not None:
        raise ValueError('이미 총괄 AI 회수 보고서가 있습니다. 기존 보고서를 검토하세요.')
    report = collect_chief_review(store, artifact_id, cancel=cancel)
    return {**report, 'task_id': task_id,
            'recovered_saved_worker_result': True,
            'worker_reexecuted': False, 'owner_approval_required': True}


def list_interrupted_chief_reviews(store, *, limit: int = 100) -> list[dict]:
    """Read-only T17 recovery candidates; never infer success from a running row.

    Include only exactly one audited, pending employee artifact linked to an
    approved chief order. An interrupted model run with no durable artifact is
    deliberately excluded; it cannot be safely rerun without owner direction.
    """
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('검토 복구 후보 조회는 1~100건입니다.')
    from desktop import company_chief_review_leases as review_leases
    locked_artifacts={item['artifact_id'] for item in review_leases.snapshot(store)}
    candidates = []
    for task in sorted(store.list_tasks(), key=lambda row: int(row['id'])):
        tid = int(task['id'])
        if task['status'] != 'in_progress' or store.read_chief_task_order(tid) is None:
            continue
        artifacts = store.list_task_artifacts(tid)
        if len(artifacts) != 1 or artifacts[0]['review_status'] != 'pending':
            continue
        artifact_id = int(artifacts[0]['id'])
        if store.find_chief_task_report(artifact_id) is not None:
            continue
        if artifact_id in locked_artifacts:
            continue
        try:
            provenance = store.chief_task_report_context(artifact_id)
        except ValueError:
            # Non-chief/failed-run artifacts must not be presented as resumable.
            continue
        if int(provenance['task_id']) != tid:
            continue
        candidates.append({'task_id': tid, 'artifact_id': artifact_id,
                           'title': task['title'], 'worker_reexecuted': False})
        if len(candidates) == limit:
            break
    return candidates


def inspect_recovery_state(store, *, max_runs: int = 200) -> dict:
    """Read-only operator status for both independent crash windows.

    A 'running' row can be a LIVE subprocess or a crash remnant; this API
    never assumes it is dead and never closes it. The existing native 'AI 업무
    실행' tab requires an explicit owner confirmation and a live-process check
    before invoking LocalStore.recover_interrupted_task_run().
    """
    store.require_permission('company:manage')
    if type(max_runs) is not int or not 1 <= max_runs <= 200:
        raise ValueError('실행 감사 조회는 1~200건이어야 합니다.')
    # Filter unfinished rows at the database before imposing audit bounds.
    # Otherwise >200 recently completed runs hide older running workers.
    with store._connect() as con:
        rows = con.execute(
            """SELECT id, task_id, employee_id, status, started_at
               FROM company_task_runs WHERE status='running'
               ORDER BY id DESC LIMIT ?""", (max_runs + 1,)).fetchall()
    running = [{
        'run_id': int(item[0]),
        'task_id': int(item[1]),
        'employee_id': int(item[2]),
        'status': item[3],
        'started_at': item[4],
    } for item in rows[:max_runs]]
    # The model-call journal also contains diagnostics and chief calls not
    # represented in company_task_runs. Keep older unfinished calls visible
    # without deciding that their processes are dead or retrying them.
    with store._connect() as con:
        model_rows = con.execute(
            """SELECT id,employee_id,model_id,started_at
               FROM ai_model_call_history WHERE status='running'
               ORDER BY id DESC LIMIT ?""", (max_runs + 1,)).fetchall()
    running_models = [dict(call_id=int(row[0]), employee_id=int(row[1]),
                           model_id=int(row[2]), started_at=str(row[3]))
                      for row in model_rows[:max_runs]]
    from desktop import company_chief_review_leases as review_leases
    return {'running_worker_runs': running,
            'running_worker_runs_truncated': len(rows) > max_runs,
            'running_model_calls': running_models,
            'running_model_calls_truncated': len(model_rows) > max_runs,
            'pending_chief_reviews': list_interrupted_chief_reviews(store),
            'chief_review_leases': review_leases.snapshot(store),
            'run_scan_limit': max_runs,
            'requires_owner_process_confirmation': True,
            'changed_task_state': False,
            'auto_reran_worker': False}


def recover_interrupted_chief_review_queue(store, *, limit: int = 3,
                                           cancel: threading.Event | None = None,
                                           expected_task_ids: tuple[int, ...] | None = None) -> dict:
    """Explicit owner batch recovery: up to 3 saved worker results, chief ONLY.

    No unattended schedule, implicit approval, worker subprocess rerun,
    automatic retry, or continuing after a failed chief invocation.
    """
    assert_running_allowed(store)
    if type(limit) is not int or not 1 <= limit <= 3:
        raise ValueError('한 번에 복구할 총괄 검토는 1~3건입니다.')
    if cancel is not None and cancel.is_set():
        raise InterruptedError('검토 복구 대기열 시작 전에 관리자가 취소했습니다.')
    if expected_task_ids is not None:
        if (type(expected_task_ids) is not tuple or not expected_task_ids
                or len(expected_task_ids) > limit
                or any(type(tid) is not int or tid <= 0 for tid in expected_task_ids)
                or len(set(expected_task_ids)) != len(expected_task_ids)):
            raise ValueError('관리자가 확인한 복구 업무 번호 목록이 올바르지 않습니다.')
    candidates = list_interrupted_chief_reviews(store, limit=limit)
    if not candidates:
        raise ValueError('관리자가 재개할 수 있는 중단 총괄 검토가 없습니다.')
    if expected_task_ids is not None and tuple(
            item['task_id'] for item in candidates) != expected_task_ids:
        raise ValueError('관리자가 확인한 복구 대상이 변경되었습니다. 목록을 다시 확인하고 승인하세요.')
    reports = []
    for index, candidate in enumerate(candidates):
        if cancel is not None and cancel.is_set():
            raise InterruptedError('중단 검토 복구 대기열이 관리자에 의해 취소됐습니다.')
        assert_running_allowed(store)
        if expected_task_ids is not None:
            # A different window may have changed the saved review queue
            # after the first chief model call. Never execute a newly queued
            # item that was absent from the owner's original confirmation.
            remaining = tuple(row['task_id'] for row in
                list_interrupted_chief_reviews(store, limit=len(expected_task_ids)-index))
            if remaining != expected_task_ids[index:]:
                raise ValueError('관리자가 확인한 복구 대상이 실행 중 변경됐습니다. 다시 확인하고 승인하세요.')
        # Re-evaluate persisted order, run and report on EACH iteration.
        # Existing saved worker artifact is never regenerated.
        reports.append(recover_interrupted_chief_review(
            store, candidate['task_id'], cancel=cancel))
    return {'reports': reports,
            'task_ids': [int(r['task_id']) for r in reports],
            'recovered_reviews': len(reports),
            'pending_owner_review': len(reports),
            'worker_reexecuted': False,
            'auto_approved': False, 'tasks_finalized': False}


def review_chief_feedback(store, report_id: int, decision: str, note: str = '') -> None:
    """Owner records acceptance/rejection of chief advice, NEVER task completion."""
    store.require_permission('company:manage')
    if type(report_id) is not int or report_id <= 0:
        raise ValueError('총괄 보고서 번호가 올바르지 않습니다.')
    if decision not in ('accepted', 'rejected'):
        raise ValueError('총괄 보고서 검수는 수락 또는 반려만 가능합니다.')
    store.review_chief_task_report(report_id, decision, note)


def finalize_approved_artifact(store, artifact_id: int) -> int:
    """Only the owner may explicitly complete a task backed by an approved result.

    The immutable artifact must come from a successful audited staff run.
    This action never creates revenue or automatically reviews the result.
    Existing task state-machine/dependency checks remain authoritative.
    """
    store.require_permission('company:manage')
    if type(artifact_id) is not int or artifact_id <= 0:
        raise ValueError('완료할 결과물 번호가 올바르지 않습니다.')
    with store._connect() as con:
        row = con.execute("""SELECT a.task_id,a.review_status,r.status,t.status
            FROM company_task_artifacts a
            JOIN company_task_runs r ON r.id=a.run_id AND r.task_id=a.task_id
            JOIN company_tasks t ON t.id=a.task_id
            WHERE a.id=?""",(artifact_id,)).fetchone()
        if row is not None and con.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='aiwack_department_plan_steps'""").fetchone():
            step=con.execute("""SELECT s.plan_id,p.state,s.worker_employee_id
                FROM aiwack_department_plan_steps s
                JOIN aiwack_department_plans p ON p.id=s.plan_id
                WHERE s.task_id=?""",(row[0],)).fetchone()
            if step is not None:
                evidence=con.execute("""SELECT c.owner_decision FROM company_chief_task_reports c
                    JOIN company_task_artifacts a ON a.id=c.artifact_id
                    JOIN company_task_runs r ON r.id=a.run_id
                    WHERE a.id=? AND r.employee_id=? AND r.status='success'""",
                    (artifact_id,step[2])).fetchone()
                if step[1]!='approved' or evidence is None or evidence[0]!='accepted':
                    raise ValueError('부서 협업 총괄 보고서를 소유자가 수락하기 전에는 업무 완료 불가합니다.')
    if row is None:
        raise ValueError('업무에 연결된 실제 AI 실행 결과물을 찾지 못했습니다.')
    task_id,review_state,run_state,task_state = row
    if review_state != 'approved' or run_state != 'success':
        raise ValueError('실제 실행 성공 기록과 관리자 승인 결과물이 모두 필요합니다.')
    if task_state != 'in_progress':
        raise ValueError('진행 중인 업무만 승인된 결과물로 완료할 수 있습니다.')
    store.set_task_status(int(task_id),'done')
    return int(task_id)


def eligible_model_employees(store) -> list[dict]:
    """Return only owners' existing draft profiles; never invent running workers."""
    store.require_permission('agents:manage')
    return [{'id': int(e['id']), 'name': e['display_name']}
            for e in store.list_employee_records() if e['lifecycle'] == 'draft']


def connect_employee_model(store, employee_id: int, config) -> int:
    """Validate trusted local paths and bind one existing employee, with rollback.

    Model registration itself is not inference. Refuse implicit replacement of
    an existing employee assignment; require a deliberate native settings edit.
    """
    from desktop.model_runtime import validate_config
    store.require_permission('agents:manage')
    if type(employee_id) is not int or employee_id <= 0:
        raise ValueError('연결할 AI 직원 번호가 올바르지 않습니다.')
    if employee_id not in {p['id'] for p in eligible_model_employees(store)}:
        raise ValueError('선택한 직원이 없거나 비활성화됐습니다.')
    if store.read_employee_model(employee_id) is not None:
        raise ValueError('이미 모델이 배정돼 있습니다. 모델 변경은 직원별 모델 설정에서 승인하세요.')
    clean = validate_config(config)
    model_id = store.add_local_model(clean)
    try:
        # Re-check before binding, for concurrent admin changes.
        if store.read_employee_model(employee_id) is not None:
            raise ValueError('다른 설정 창에서 이미 모델이 배정됐습니다.')
        store.set_employee_model(employee_id, model_id)
    except Exception:
        # No orphan registration on failure, even after concurrent edits.
        try:
            store.delete_local_model(model_id)
        except (ValueError, PermissionError):
            pass
        raise
    return model_id


def probe_employee_model(store, employee_id: int, *, cancel: threading.Event | None = None) -> str:
    """Call REAL local configured runner, recording a genuine employee-model audit.

    No result is stored as an approved task, revenue or completed project.
    A synthetic subprocess test still proves only the adapter, not GGUF inference.
    """
    from desktop.employee_model_runtime import invoke_employee_model
    assert_running_allowed(store)
    if type(employee_id) is not int or employee_id <= 0:
        raise ValueError('올바른 직원 번호를 선택하세요.')
    if employee_id not in {p['id'] for p in eligible_model_employees(store)}:
        raise ValueError('직원이 없거나 비활성화됐습니다.')
    if store.read_employee_model(employee_id) is None:
        raise ValueError('직원에게 실제 로컬 모델을 먼저 연결하세요.')
    if cancel is not None and cancel.is_set():
        raise InterruptedError('실행 전 취소되었습니다.')
    reply = invoke_employee_model(store, employee_id,
        '당신은 AIWACK 로컬 AI 직원입니다. 이 요청은 연결 진단입니다. '
        '한국어로 두 문장으로 자신이 실행됐음을 설명하고, 실제 사업 실행이나 매출이 '
        '발생했다고 주장하지 마세요.', timeout=60, cancel=cancel)
    if cancel is not None and cancel.is_set():
        raise InterruptedError('관리자 취소 후의 결과는 폐기합니다.')
    if not reply.strip():
        raise RuntimeError('로컬 모델에서 빈 텍스트가 반환됐습니다.')
    return reply[:20000]
