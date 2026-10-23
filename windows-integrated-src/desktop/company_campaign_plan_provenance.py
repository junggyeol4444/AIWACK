"""15부서 총괄 실제 GGUF 계획의 5그룹 호출·실패 원본 보존형 조회.

기존 company_wide_campaign 계획과 SQLite 모델 호출 기록을 그대로 사용한다.
모델 출력 생성·가짜 채움·외부 실행·관리자 승인 대행을 하지 않는다.
"""
from __future__ import annotations

import hashlib
import json

from desktop import company_wide_campaign as wide


def snapshot(store, campaign_id: int) -> dict:
    """Check all five immutable staged chief groups against actual model-call IDs."""
    store.require_permission('company:manage')
    if type(campaign_id) is not int or campaign_id <= 0:
        raise ValueError('실제 회사 전체 협업 번호는 양의 정수여야 합니다.')
    with store._connect() as con:
        wide.initialize(con)
        campaign = con.execute('''SELECT source_task_id,source_fingerprint,
            chief_employee_id,state FROM aiwack_wide_campaigns WHERE id=?''',
            (campaign_id,)).fetchone()
        if campaign is None:
            raise ValueError('총괄 회사 전체 협업 원본이 없습니다.')
        source_id, fingerprint, chief, state = campaign
        current_fingerprint, _ = wide._source(store, con, source_id)
        actual_chief, model, groups = wide._staff_roster(con)
        roster_seal = wide._roster_sha256(actual_chief, model, groups)
        if fingerprint != current_fingerprint or chief != actual_chief:
            raise ValueError('총괄 계획의 원본 업무 또는 총괄 직원이 변경됐습니다.')
        if state not in ('draft', 'approved', 'rejected'):
            raise ValueError('총괄 계획의 상태가 잘못됐습니다.')
        if state == 'approved':
            wide._assert_campaign_plan_matches_genuine_staging(store, con, campaign_id)
        items = []
        successful_call_ids = set()
        for start in range(0, 15, 3):
            part = groups[start:start + 3]
            if len(part) != 3:
                raise ValueError('총괄 15부서 5그룹 조직 정보가 부족합니다.')
            proof = wide._verified_staged_group(con, source_id, start, fingerprint,
                                                 roster_seal, chief, model, part)
            if proof is None:
                raise ValueError(f'총괄 실제 GGUF 계획 {start//3+1}/5 그룹 감사가 없습니다.')
            parsed, calls = proof
            if set(calls) != {name for _, name, _, _ in part}:
                raise ValueError('실제 호출 부서와 저장된 총괄 계획이 다릅니다.')
            unique = set(calls.values())
            if len(unique) not in (1, 3):
                raise ValueError('한 그룹에 전체 호출과 일부 부서 재호출이 혼합됐습니다.')
            kind = 'three_departments' if len(unique) == 1 else 'single_department'
            requested_names = ','.join(name for _, name, _, _ in part)
            entries = []
            for _, name, _, _ in part:
                call_id = calls[name]
                audit = con.execute('''SELECT a.attempt_kind,a.department_names,
                    a.parsed,a.error_kind,a.output_sha256,a.output_chars,
                    h.employee_id,h.model_id,h.status,h.output_chars
                    FROM aiwack_wide_chief_plan_attempts a
                    JOIN ai_model_call_history h ON h.id=a.model_call_id
                    WHERE a.source_task_id=? AND a.chief_employee_id=?
                      AND a.model_call_id=?''', (source_id, chief, call_id)).fetchone()
                if audit is None:
                    raise ValueError('총괄 실제 모델 호출의 불변 감사가 없습니다.')
                audit_kind, names, parsed_ok, error, output_sha, chars, worker, used_model, status, model_chars = audit
                if (audit_kind != kind or
                    names != (requested_names if kind == 'three_departments' else name) or
                    parsed_ok != 1 or error or worker != chief or used_model != model or
                    status != 'success' or not isinstance(output_sha, str) or
                    len(output_sha) != 64 or type(chars) is not int or chars <= 0 or
                    type(model_chars) is not int or model_chars <= 0):
                    raise ValueError('총괄 모델 호출 유형·원본 감사·직원/모델 ID가 불일치합니다.')
                title, instruction = parsed[name]
                entries.append({'department': name, 'model_call_id': call_id,
                                'output_sha256': output_sha, 'output_chars': chars,
                                'title_sha256': hashlib.sha256(title.encode('utf-8')).hexdigest(),
                                'instruction_sha256': hashlib.sha256(instruction.encode('utf-8')).hexdigest()})
            if successful_call_ids.intersection(unique):
                raise ValueError('서로 다른 총괄 계획 그룹이 같은 모델 호출을 재사용했습니다.')
            successful_call_ids.update(unique)
            items.append({'group': start//3 + 1, 'call_kind': kind,
                          'unique_real_chief_calls': len(unique), 'departments': entries})
        failed = con.execute('''SELECT model_call_id,attempt_kind,department_names,
            output_sha256,output_chars,error_kind
            FROM aiwack_wide_chief_plan_attempts
            WHERE source_task_id=? AND chief_employee_id=? AND parsed=0
            ORDER BY id''', (source_id, chief)).fetchall()
        # The append-only failure mirror must match every real model call.
        mirror_rows = con.execute('''SELECT model_call_id,attempt_kind,requested_departments,
            output_sha256,output_chars,error_reason
            FROM aiwack_wide_chief_rejected_attempts
            WHERE source_task_id=? AND chief_employee_id=? ORDER BY id''',
            (source_id, chief)).fetchall()
        mirror = {row[0]: row for row in mirror_rows}
        if (len(mirror) != len(mirror_rows)
                or {row[0] for row in failed} != set(mirror)):
            raise ValueError('실패 총괄 호출의 불변 이중 감사 기록이 누락되거나 중복됐습니다.')
        rejected = []
        for row in failed:
            call_id, attempt_kind, requested, digest, chars, error = row
            counterpart = mirror[call_id]
            try:
                expected_names = json.dumps(requested.split(','), ensure_ascii=False,
                                            separators=(',', ':'))
            except (TypeError, AttributeError) as exc:
                raise ValueError('실패 총괄 호출 부서 감사가 손상됐습니다.') from exc
            if (counterpart[1] != attempt_kind or counterpart[2] != expected_names
                    or counterpart[3] != digest or counterpart[4] != chars
                    or counterpart[5][:100] != error):
                raise ValueError('실패 총괄 호출의 원본 SHA·부서·사유 이중 감사가 다릅니다.')
            actual = con.execute('''SELECT employee_id,model_id,status,output_chars
                FROM ai_model_call_history WHERE id=?''', (call_id,)).fetchone()
            if (actual is None or actual[0] != chief or actual[1] != model
                    or actual[2] != 'success' or type(actual[3]) is not int
                    or actual[3] <= 0 or attempt_kind not in
                    ('three_departments', 'single_department')
                    or not isinstance(requested, str) or not requested
                    or not isinstance(digest, str)
                    or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)
                    or type(chars) is not int or chars <= 0
                    or not isinstance(error, str) or not error):
                raise ValueError('실패한 실제 총괄 모델 호출의 불변 감사 출처가 손상됐습니다.')
            rejected.append({'model_call_id': call_id, 'attempt_kind': attempt_kind,
                             'requested_departments': requested, 'output_sha256': digest,
                             'output_chars': chars, 'error_kind': error})
    payload = {'campaign_id': campaign_id, 'source_task_id': source_id,
               'chief_employee_id': chief, 'chief_model_id': model,
               'plan_state': state, 'verified_departments': 15,
               'verified_plan_groups': len(items), 'verified_chief_call_count': len(successful_call_ids),
               'groups': items, 'failed_attempts_preserved': rejected,
               'failed_attempts_model_provenance_checked': True,
               'sqlite_model_call_audit_checked': True,
               'independent_gguf_binary_verified': False,
               'physical_windows_10_11_exe_verified': False,
               'external_transactions_executed': False}
    seal = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    payload['snapshot_sha256'] = hashlib.sha256(seal.encode('utf-8')).hexdigest()
    return payload
