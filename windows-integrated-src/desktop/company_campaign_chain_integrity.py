"""실제 5그룹→30업무→총괄 최종보고→관리자 인계의 동일 원본 연결 검사.

SQLite 및 로컬 승인 파일의 기존 감사 API만 읽는다. 모델 호출·승인·외부
결제·전송·게시를 수행하지 않으며 독립 GGUF/Windows 실검증으로 간주하지 않는다.
"""
from __future__ import annotations

import hashlib
import hmac
import json


def _positive_id(value) -> bool:
    return type(value) is int and value > 0


def _sha256(value) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(character in '0123456789abcdef' for character in value))


def snapshot(store, campaign_id: int) -> dict:
    """서로 다른 캠페인/보고서/인계 파일을 합쳐 성공 처리하지 않는다."""
    store.require_permission('company:manage')
    if type(campaign_id) is not int or campaign_id <= 0:
        raise ValueError('회사 전체 협업 번호는 양의 정수여야 합니다.')

    from desktop.company_campaign_plan_provenance import snapshot as plan_snapshot

    plan = plan_snapshot(store, campaign_id)
    progress = store.verified_full_company_progress(campaign_id)
    report = store.find_campaign_final_report(campaign_id)
    dossier = store.find_owner_approved_final_dossier_by_campaign(campaign_id)

    if (plan.get('campaign_id') != campaign_id
            or plan.get('plan_state') != 'approved'
            or plan.get('verified_plan_groups') != 5
            or plan.get('verified_departments') != 15
            or type(plan.get('verified_chief_call_count')) is not int
            or not 5 <= plan['verified_chief_call_count'] <= 15
            or not _positive_id(plan.get('source_task_id'))
            or not _positive_id(plan.get('chief_employee_id'))
            or not _sha256(plan.get('snapshot_sha256'))
            or plan.get('failed_attempts_model_provenance_checked') is not True
            or plan.get('sqlite_model_call_audit_checked') is not True):
        raise ValueError('실제 총괄 5그룹·15부서 승인 원본 연결 오류')
    if (progress.get('campaign_id') != campaign_id
            or progress.get('state') != 'approved'
            or progress.get('verified_completed_tasks') != 30
            or progress.get('verified_distinct_departments') != 15
            or progress.get('verified_distinct_workers') != 30
            or progress.get('verified_genuine_prefix_tasks') != 30
            or progress.get('verified_chief_model_call_links') != 30
            or progress.get('all_30_tasks_evidence_verified') is not True
            or progress.get('all_30_chief_model_call_links_verified') is not True):
        raise ValueError('30업무 직원·총괄 실제 호출 및 관리자 승인 연결 오류')
    if (not isinstance(report, dict) or report.get('campaign_id') != campaign_id
            or report.get('decision') != 'accepted'
            or report.get('all_30_model_call_and_owner_review_audits_verified') is not True
            or not _positive_id(report.get('id'))
            or not _positive_id(report.get('chief_model_call_id'))
            or report.get('chief_employee_id') != plan['chief_employee_id']
            or not _sha256(report.get('report_sha256'))
            or not _sha256(report.get('evidence_sha256'))):
        raise ValueError('총괄 실제 모델 최종보고·관리자 승인 연결 오류')
    if (not isinstance(dossier, dict) or dossier.get('campaign_id') != campaign_id
            or dossier.get('owner_final_approved') is not True
            or dossier.get('verified_approved_employee_steps') != 30
            or dossier.get('final_report_id') != report['id']
            or not _positive_id(dossier.get('id'))
            or not _sha256(dossier.get('file_sha256'))
            or type(dossier.get('byte_count')) is not int
            or not 1 <= dossier['byte_count'] <= 1024 * 1024):
        raise ValueError('최종 인계와 승인된 총괄 보고서가 동일하지 않습니다.')

    receipt = {
        'format': 'AIWACK_LOCAL_GENUINE_CAMPAIGN_CHAIN_V1',
        'campaign_id': campaign_id,
        'source_task_id': plan['source_task_id'],
        'chief_employee_id': plan['chief_employee_id'],
        'five_group_plan_sha256': plan['snapshot_sha256'],
        'verified_distinct_chief_plan_calls': plan['verified_chief_call_count'],
        'verified_approved_tasks': 30,
        'verified_departments': 15,
        'chief_final_report_id': report['id'],
        'chief_final_model_call_id': report['chief_model_call_id'],
        'chief_final_report_sha256': report['report_sha256'],
        'thirty_task_evidence_sha256': report['evidence_sha256'],
        'owner_approved_dossier_id': dossier['id'],
        'owner_approved_dossier_sha256': dossier['file_sha256'],
        'sqlite_and_local_file_provenance_checked': True,
        'independent_gguf_binary_verified': False,
        'physical_windows_10_11_gui_verified': False,
        'uninterrupted_24h_operation_verified': False,
        'external_pg_bank_transactions_verified': False,
        'final_T01_T20_acceptance_passed': False,
    }
    canonical = json.dumps(receipt, ensure_ascii=False, sort_keys=True,
                           separators=(',', ':')).encode('utf-8')
    receipt['receipt_sha256'] = hashlib.sha256(canonical).hexdigest()
    return receipt


def verify_receipt(store, campaign_id: int, receipt: dict) -> dict:
    """저장된 인계 지문과 현재 SQLite/파일 원본을 다시 대조한다.

    관리자 승인·모델 실행·외부 전송을 하지 않는다. 과거에 발급한 JSON이
    자체 SHA만 맞아도 현재 원본과 다르면 실패 처리한다.
    """
    if type(campaign_id) is not int or campaign_id <= 0:
        raise ValueError('회사 전체 협업 번호는 양의 정수여야 합니다.')
    if not isinstance(receipt, dict):
        raise ValueError('30업무 최종 인계 지문 형식이 올바르지 않습니다.')
    current = snapshot(store, campaign_id)
    if set(receipt) != set(current):
        raise ValueError('최종 인계 지문의 필드가 원본과 다릅니다.')
    candidate = dict(receipt)
    digest = candidate.pop('receipt_sha256', None)
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError('최종 인계 지문 SHA256이 누락됐습니다.')
    canonical = json.dumps(candidate, ensure_ascii=False, sort_keys=True,
                           separators=(',', ':')).encode('utf-8')
    recalculated = hashlib.sha256(canonical).hexdigest()
    if not hmac.compare_digest(digest, recalculated):
        raise ValueError('최종 인계 지문이 변경됐습니다.')
    if not hmac.compare_digest(digest, current['receipt_sha256']):
        raise ValueError('최종 인계 지문과 현재 승인 원본이 다릅니다.')
    return {'verified': True, 'campaign_id': campaign_id,
            'receipt_sha256': digest, 'read_only': True,
            'independent_gguf_binary_verified': False,
            'physical_windows_10_11_gui_verified': False,
            'final_T01_T20_acceptance_passed': False}

def export_receipt_json(store, campaign_id: int) -> str:
    """Export a read-only canonical receipt; no model or owner action."""
    receipt = snapshot(store, campaign_id)
    return json.dumps(receipt, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False) + '\n'


def verify_receipt_json(store, campaign_id: int, raw: str) -> dict:
    """Strictly verify a previously exported local receipt against live sources.

    Duplicate JSON keys, NaN/Infinity, extra fields and cross-campaign
    substitution are rejected. This is not a signature or GGUF binary test.
    """
    if not isinstance(raw, str) or not 0 < len(raw.encode('utf-8')) <= 65536:
        raise ValueError('최종 인계 JSON의 형식 또는 크기가 올바르지 않습니다.')

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('최종 인계 JSON에 중복된 필드가 있습니다.')
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError('최종 인계 JSON에 비표준 숫자가 있습니다: ' + value)

    try:
        receipt = json.loads(raw, object_pairs_hook=unique_pairs,
                             parse_constant=invalid_constant)
    except (TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('최종 인계 JSON을 해석할 수 없습니다.') from exc
    return verify_receipt(store, campaign_id, receipt)
