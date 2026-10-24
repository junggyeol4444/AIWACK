"""30업무 재개를 위한 읽기 전용 실원본 사전 점검.

모델 실행/관리자 승인/SQLite 수정/복구를 수행하지 않는다. 과거 실행 기록이
남은 단계를 자동 재호출하지 않으며 진행 중 프로세스를 종료하지 않는다.
"""
from __future__ import annotations


def _task_audit(store, task_id: int) -> dict:
    """과거 모델 실행·결과물이 존재하면 자동 중복 실행을 금지한다."""
    runs = store.list_task_runs(task_id)
    artifacts = store.list_task_artifacts(task_id)
    return {'existing_run_count': len(runs),
            'existing_artifact_count': len(artifacts),
            'running_run_count': sum(r.get('status') == 'running' for r in runs),
            'has_prior_execution': bool(runs or artifacts)}


def snapshot(store, campaign_id: int, *, require_genuine_provenance: bool = True) -> dict:
    """현재 30업무의 실제 원본만 조회한다. 상태 판정은 보수적으로 실패 차단."""
    store.require_permission('company:manage')
    if type(campaign_id) is not int or campaign_id <= 0:
        raise ValueError('30업무 협업 번호는 양의 정수여야 합니다.')
    plan = store.read_full_company_campaign(campaign_id)
    steps = plan.get('steps')
    if (plan.get('id') != campaign_id or not isinstance(steps, list)
            or len(steps) != 30
            or [s.get('ordinal') for s in steps] != list(range(1, 31))):
        raise ValueError('30업무 순서·배정 원본이 누락되거나 중복되었습니다.')
    if plan.get('state') != 'approved':
        return {'campaign_id': campaign_id, 'state': 'blocked',
                'reason': '관리자가 승인한 30업무 계획이 아닙니다.',
                'next_task_id': None, 'next_ordinal': None,
                'verified_completed_tasks': 0, 'executed': False,
                'automatically_retried': False, 'read_only': True}
    if (len({s.get('task_id') for s in steps}) != 30
            or any(type(s.get('task_id')) is not int or s['task_id'] <= 0
                   for s in steps)):
        raise ValueError('승인된 30업무의 실제 배정 번호가 누락되거나 중복되었습니다.')
    progress = store.verified_full_company_progress(campaign_id)
    if progress.get('campaign_id') != campaign_id:
        raise ValueError('30업무 진행 원본의 협업 번호가 다릅니다.')
    prefix = progress.get('verified_genuine_prefix_tasks')
    count = progress.get('verified_completed_tasks')
    if (type(prefix) is not int or type(count) is not int
            or not 0 <= prefix <= 30 or not 0 <= count <= 30):
        raise ValueError('실제 총괄 모델/관리자 승인 진행 원본이 손상됐습니다.')
    first_pending = next((s for s in steps if s.get('task_status') != 'done'), None)
    if first_pending is None:
        # 완료 표시는 승인된 15부서/30개 모델 호출 원본까지 연결돼야 한다.
        # 단순 30개 상태 플래그만으로 재개·종료 성공을 주장하지 않는다.
        complete = (prefix == 30 and count == 30
                    and progress.get('state') == 'approved'
                    and progress.get('total_tasks') == 30
                    and progress.get('verified_distinct_departments') == 15
                    and progress.get('verified_chief_model_call_links') == 30
                    and progress.get('next_task_id') is None
                    and progress.get('all_30_tasks_evidence_verified') is True
                    and progress.get('all_30_chief_model_call_links_verified') is True)
        return {'campaign_id': campaign_id,
                'state': 'completed' if complete else 'blocked',
                'reason': '30업무 실제 승인 증빙 확인' if complete else '완료 표시와 실제 승인 증빙이 다릅니다.',
                'next_task_id': None, 'next_ordinal': None,
                'verified_completed_tasks': count,
                'verified_genuine_prefix_tasks': prefix,
                'executed': False, 'automatically_retried': False,
                'read_only': True}
    # 완료된 30업무는 반드시 연속 접두 구간이어야 한다. 첫 미완료 이후의
    # 완료/진행 표시 또는 기존 실행 기록이 있으면 관리자 확인 없이 재개 불가.
    ordinal = first_pending['ordinal']
    future_anomalies = []
    for later in steps[ordinal:]:
        later_id = later['task_id']
        if later.get('task_status') != 'todo':
            future_anomalies.append(later['ordinal'])
        elif _task_audit(store, later_id)['has_prior_execution']:
            future_anomalies.append(later['ordinal'])
    task_id = first_pending.get('task_id')
    if type(task_id) is not int or task_id <= 0:
        raise ValueError('실제 직원 업무 번호가 올바르지 않습니다.')
    audit = _task_audit(store, task_id)
    status = first_pending.get('task_status')
    reasons = []
    if status != 'todo':
        reasons.append('현재 업무 상태가 미실행(todo)이 아닙니다: ' + str(status))
    if future_anomalies:
        reasons.append('후속 업무의 선행 실행·완료 흔적이 있어 순서 재개를 차단합니다: '
                       + ','.join(map(str, future_anomalies)))
    if audit['has_prior_execution']:
        reasons.append('기존 실행·결과물이 존재하여 자동 재실행을 금지합니다.')
    if count != ordinal - 1:
        reasons.append('직전 직원 결과·관리자 승인 원본 연결이 부족합니다.')
    if require_genuine_provenance and prefix != ordinal - 1:
        reasons.append('직전 총괄 실제 모델 호출 연결이 부족합니다.')
    if progress.get('next_task_id') != task_id:
        reasons.append('다음 실행 대상이 기존 진행 원본과 다릅니다.')
    return {'campaign_id': campaign_id, 'state': 'blocked' if reasons else 'ready',
            'reason': ' / '.join(reasons) if reasons else '다음 한 업무만 관리자 확인 후 실행 가능',
            'next_task_id': task_id, 'next_ordinal': ordinal,
            'current_task_status': status, 'verified_completed_tasks': count,
            'verified_genuine_prefix_tasks': prefix,
            **audit, 'executed': False, 'automatically_retried': False,
            'read_only': True}


def require_next(store, campaign_id: int, expected_task_id: int, *,
                 require_genuine_provenance: bool = True) -> dict:
    """실행 직전 기존 감사 상태를 재조회. 원본/프로세스 우회 불가."""
    if type(expected_task_id) is not int or expected_task_id <= 0:
        raise ValueError('실행 대상 업무 번호는 양의 정수여야 합니다.')
    result = snapshot(store, campaign_id,
                      require_genuine_provenance=require_genuine_provenance)
    if result['state'] != 'ready' or result['next_task_id'] != expected_task_id:
        raise ValueError('30업무 재개 점검 실패: ' + result['reason'])
    return result
