"""기존 AIWACK 실업무 증빙을 하나의 관리자 전용 읽기 화면에 연결한다.

원본 모델·SQLite·감사·승인 API를 그대로 호출한다. 없는 결과를 생성하지
않으며, Windows 실사용/독립 GGUF/PG/은행 실거래 성공을 추정하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3


def _digest(payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(',', ':'), default=str)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _read_section(callback) -> dict:
    """개별 업무의 실패를 성공으로 바꾸지 않고 다음 섹션은 계속 조회."""
    try:
        value = callback()
    except (ValueError, PermissionError, RuntimeError, OSError, sqlite3.Error,
            KeyError, TypeError) as exc:
        return {'state': 'unavailable', 'error_type': type(exc).__name__,
                'reason': str(exc)[:350]}
    if value is None:
        return {'state': 'not_recorded'}
    return {'state': 'observed', 'data': value}


def snapshot(store, campaign_id: int, business_id: int | None = None) -> dict:
    """현재 로컬 원본 상태를 다시 조회한다. 호출/거래/승인 실행 없음.

    상태 'observed'는 API가 조회됐다는 뜻일 뿐 Windows 또는 외부 공급자
    실검증의 PASS 판정이 아니다. 캠페인/사업의 독립된 증빙을 섞지 않는다.
    """
    store.require_permission('company:manage')
    if type(campaign_id) is not int or campaign_id <= 0:
        raise ValueError('30업무 협업 번호는 양의 정수여야 합니다.')
    if business_id is not None and (type(business_id) is not int or business_id <= 0):
        raise ValueError('사업 번호는 양의 정수여야 합니다.')

    from desktop import company_campaign_plan_provenance as provenance
    from desktop import company_continuity as continuity
    from desktop import company_staff_metrics as staff_metrics
    from desktop import company_campaign_chain_integrity as chain_integrity
    from desktop import company_campaign_final_leases as final_leases
    from desktop import company_campaign_final_report as final_reports

    sections = {}

    def plan():
        proof = provenance.snapshot(store, campaign_id)
        return {
            'plan_state': proof['plan_state'],
            'five_group_snapshot_sha256': proof['snapshot_sha256'],
            'actual_chief_group_count': proof['verified_plan_groups'],
            'departments': proof['verified_departments'],
            'actual_chief_call_count': proof['verified_chief_call_count'],
            'failed_attempt_count': len(proof['failed_attempts_preserved']),
            'independent_gguf_binary_verified': False,
        }

    def progress():
        result = store.verified_full_company_progress(campaign_id)
        return {
            'verified_completed_tasks': result['verified_completed_tasks'],
            'verified_distinct_departments': result['verified_distinct_departments'],
            'verified_genuine_prefix_tasks': result.get('verified_genuine_prefix_tasks', 0),
            'all_30_tasks_evidence_verified': bool(result.get('all_30_tasks_evidence_verified')),
            'all_30_chief_model_call_links_verified': bool(
                result.get('all_30_chief_model_call_links_verified')),
        }

    def report():
        result = store.find_campaign_final_report(campaign_id)
        if result is None:
            return None
        return {'report_id': result['id'], 'decision': result['decision'],
                'report_sha256': result['report_sha256'],
                'chief_model_call_id': result['chief_model_call_id'],
                'all_30_model_call_and_owner_review_audits_verified':
                    result['all_30_model_call_and_owner_review_audits_verified'],
                'independent_gguf_binary_verified': False}

    def dossier():
        result = store.find_owner_approved_final_dossier_by_campaign(campaign_id)
        if result is None:
            return None
        return {'dossier_id': result['id'], 'file_sha256': result['file_sha256'],
                'byte_count': result['byte_count'],
                'owner_final_approved': result['owner_final_approved'],
                'verified_approved_employee_steps': result['verified_approved_employee_steps'],
                'physical_windows_10_11_exe_verified': False}

    def staff():
        return staff_metrics.snapshot(store)

    def signed_payments():
        return store.signed_payment_reconciliation_summary(business_id)

    def finance():
        if business_id is None:
            return None
        return {'close_preview': store.preview_business_financial_close(business_id),
                'recorded_period_closes': store.list_business_financial_closes(business_id)}

    def tools():
        return {
            'registered': store.list_registered_ai_tools(),
            'approved_local_read_executions': store.approved_local_read_tool_history(30),
            'approved_windows_version_executions': store.approved_windows_version_tool_history(30),
        }

    sections['campaign_resume_and_duplicate_run_gate'] = _read_section(
        lambda: store.inspect_full_company_resume_gate(campaign_id))
    sections['linked_local_approval_chain'] = _read_section(
        lambda: chain_integrity.snapshot(store, campaign_id))
    sections['chief_five_group_plan'] = _read_section(plan)
    sections['worker_chief_30_tasks'] = _read_section(progress)
    sections['real_chief_final_report'] = _read_section(report)
    # Preserve cross-window GGUF execution state and its immutable recovery
    # journal as separate observations. An aged lock is NOT a dead subprocess.
    sections['real_chief_final_report_attempt_audit'] = _read_section(
        lambda: final_reports.inspect_final_model_attempt_chain(store,campaign_id))
    sections['chief_final_format_retry_budget'] = _read_section(
        lambda: final_reports.remaining_final_report_model_attempts(
            store, campaign_id))
    sections['final_report_cross_window_leases'] = _read_section(
        lambda: {'locks_for_campaign': [
            lock for lock in final_leases.snapshot(store,100)
            if lock['campaign_id']==campaign_id],
            'manual_recovery_history': [
                rec for rec in final_leases.recovery_history(store,100)
                if rec['campaign_id']==campaign_id],
            'process_liveness_verified':False,'automatic_retry':False})
    sections['owner_final_dossier'] = _read_section(dossier)
    sections['owner_dossier_disk_recovery_inventory'] = _read_section(
        lambda: store.inspect_owner_dossier_disk_consistency(100))
    sections['staff_observed_metrics'] = _read_section(staff)
    sections['signed_payment_evidence'] = _read_section(signed_payments)
    sections['business_period_finance'] = _read_section(finance)
    sections['owner_csv_bank_reconciliation'] = _read_section(
        lambda: store.list_bank_reconciliation_batches(100))
    sections['approved_local_tools'] = _read_section(tools)
    sections['native_gui_continuity'] = _read_section(
        lambda: continuity.observed_gui_continuity(store))
    sections['actual_operational_incident_audits'] = _read_section(
        lambda: store.operational_incident_history(100))
    sections['department_real_workload'] = _read_section(
        store.department_workload_snapshot)
    sections['department_workload_owner_reviews'] = _read_section(
        lambda: store.department_workload_review_history(100))
    sections['real_chief_operations_finance_reviews'] = _read_section(
        lambda: store.chief_evidence_review_history(30))

    sections['customer_case_global_reconciliation'] = _read_section(
        lambda: store.list_customer_cases(100))
    sections['product_document_global_reconciliation'] = _read_section(
        lambda: store.list_approved_product_documents(100))

    chain_checks = {
        'same_campaign_and_final_report_dossier_provenance': (
            sections['linked_local_approval_chain']['state'] == 'observed'
            and sections['linked_local_approval_chain']['data'].get('campaign_id') == campaign_id
            and sections['linked_local_approval_chain']['data'].get(
                'sqlite_and_local_file_provenance_checked') is True),
        'five_real_chief_groups': (
            sections['chief_five_group_plan']['state'] == 'observed'
            and sections['chief_five_group_plan']['data'].get('plan_state') == 'approved'
            and sections['chief_five_group_plan']['data'].get('actual_chief_group_count') == 5
            and sections['chief_five_group_plan']['data'].get('departments') == 15),
        'thirty_owner_reviewed_steps': (
            sections['worker_chief_30_tasks']['state'] == 'observed'
            and sections['worker_chief_30_tasks']['data'].get('verified_completed_tasks') == 30
            and sections['worker_chief_30_tasks']['data'].get('verified_distinct_departments') == 15
            and sections['worker_chief_30_tasks']['data'].get('verified_genuine_prefix_tasks') == 30
            and sections['worker_chief_30_tasks']['data'].get('all_30_tasks_evidence_verified') is True
            and sections['worker_chief_30_tasks']['data'].get('all_30_chief_model_call_links_verified') is True),
        'real_chief_final_report_owner_accepted': (
            sections['real_chief_final_report']['state'] == 'observed'
            and sections['real_chief_final_report']['data'].get('decision') == 'accepted'
            and sections['real_chief_final_report']['data'].get(
                'all_30_model_call_and_owner_review_audits_verified') is True),
        'owner_approved_final_dossier': (
            sections['owner_final_dossier']['state'] == 'observed'
            and sections['owner_final_dossier']['data'].get('owner_final_approved') is True
            and sections['owner_final_dossier']['data'].get('verified_approved_employee_steps') == 30),
    }
    section_counts = {state: sum(v['state'] == state for v in sections.values())
                      for state in ('observed', 'not_recorded', 'unavailable')}
    result = {
        'format': 'AIWACK_NATIVE_OWNER_OPERATIONS_READONLY_V1',
        'local_approval_chain_checks': chain_checks,
        'local_approval_chain_complete': all(chain_checks.values()),
        'missing_or_invalid_local_chain_links': [
            name for name, valid in chain_checks.items() if not valid],
        'section_read_status_counts': section_counts,
        'campaign_id': campaign_id, 'business_id': business_id,
        'sections': sections,
        'owner_dossier_disk_consistency_verified': (
            sections['owner_dossier_disk_recovery_inventory']['state'] == 'observed'
            and sections['owner_dossier_disk_recovery_inventory']['data'].get('scan_complete') is True
            and sections['owner_dossier_disk_recovery_inventory']['data'].get(
                'all_scanned_registered_files_intact') is True
            and sections['owner_dossier_disk_recovery_inventory']['data'].get(
                'no_orphaned_files_confirmed') is True),
        'local_sqlite_audit_only': True,
        'owner_approval_executed': False,
        'independent_gguf_binary_verified': False,
        'actual_windows_10_11_gui_verified': False,
        'uninterrupted_24h_windows_operation_verified': False,
        'external_pg_bank_transactions_verified': False,
        'external_publication_or_customer_delivery_executed': False,
        'final_T01_T20_acceptance_passed': False,
    }
    result['snapshot_sha256'] = _digest(result)
    return result
