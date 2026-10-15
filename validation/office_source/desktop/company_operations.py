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
