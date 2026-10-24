"""30업무 직원/총괄 모델 호출·관리자 승인 SQLite 원본의 로컬 감사 파일.

SQLite 모델 호출 기록과 독립적인 GGUF 실행파일 증명은 다르다.
이 문서가 존재해도 Windows 실제 모델/GUI 실행 성공으로 표시하지 않는다.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path
import sqlite3

from desktop import company_wide_campaign as wide
from desktop.stage87_90_management import stopped


def initialize(con:sqlite3.Connection):
    wide.initialize(con)
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_campaign_evidence_exports(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL REFERENCES aiwack_wide_campaigns(id),
        completed_count INTEGER NOT NULL CHECK(completed_count BETWEEN 1 AND 30),
        filename TEXT NOT NULL UNIQUE,
        manifest_sha256 TEXT NOT NULL CHECK(length(manifest_sha256)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(campaign_id,completed_count))''')
    for action in ('UPDATE','DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS aiwack_campaign_evidence_exports_no_{action.lower()}
            BEFORE {action} ON aiwack_campaign_evidence_exports BEGIN
            SELECT RAISE(ABORT,'30업무 감사 파일 기록 수정·삭제 금지'); END''')


def _build(store,campaign_id:int, *, upto:int | None=None):
    plan=wide.read(store,campaign_id)
    progress=wide.verified_progress(store,campaign_id)
    current_completed=progress['verified_completed_tasks']
    completed=current_completed if upto is None else upto
    if current_completed == 0 and upto is None:
        raise ValueError('관리자 승인된 실제 직원/총괄 업무가 아직 없습니다.')
    if type(completed) is not int or not 1<=completed<=current_completed<=30:
        raise ValueError('요청된 원본 감사 단계가 실제 완료 단계보다 많거나 잘못됐습니다.')
    if progress['verified_genuine_prefix_tasks']<completed:
        raise ValueError('총괄 실제 모델 호출 기록이 검증되지 않은 업무가 있습니다.')
    entries=[]
    observed=set()
    with store._connect() as con:
        initialize(con)
        for index in range(completed):
            step=plan['steps'][index]
            proof=wide._verified_step_evidence(con,campaign_id,index+1,
                      expected_chief=plan['chief_employee_id'])
            if not proof or not wide._verified_chief_model_call_link(con,campaign_id,index+1,
                      expected_chief=plan['chief_employee_id']):
                raise ValueError('30업무 직원/총괄 모델 호출·관리자 승인 기록이 손상됐습니다.')
            row=con.execute('''SELECT r.model_call_id,rep.chief_model_call_id,
                   r.employee_id,rep.chief_employee_id,r.model_id,h1.model_id,h2.model_id,
                   h1.status,h2.status,h1.output_chars,h2.output_chars
                FROM company_task_artifacts a
                JOIN company_task_runs r ON r.id=a.run_id
                JOIN company_chief_task_reports rep ON rep.artifact_id=a.id
                JOIN ai_model_call_history h1 ON h1.id=r.model_call_id
                JOIN ai_model_call_history h2 ON h2.id=rep.chief_model_call_id
                WHERE a.id=? AND a.task_id=? AND r.task_id=?''',
                (proof['artifact_id'],step['task_id'],step['task_id'])).fetchone()
            if not row:
                raise ValueError('실제 직원 또는 총괄 모델의 감사 원문이 없습니다.')
            worker,chief,employee,chief_employee,model,worker_model,chief_model,*rest=row
            if (type(worker) is not int or type(chief) is not int or worker>=chief
                    or worker in observed or chief in observed
                    or employee!=step['employee_id'] or chief_employee!=plan['chief_employee_id']
                    or model!=worker_model or not worker_model or not chief_model
                    or rest[0]!='success' or rest[1]!='success'
                    or rest[2]<=0 or rest[3]<=0):
                raise ValueError('직원/총괄 모델 감사 기록이 승인 업무의 출처와 다릅니다.')
            observed.update((worker,chief))
            entries.append({'ordinal':index+1,'department':step['department'],
                'employee_id':employee,'task_id':step['task_id'],
                'artifact_id':proof['artifact_id'],
                'artifact_sha256':proof['artifact_sha256'],
                'chief_report_sha256':proof['chief_report_sha256'],
                'worker_call_id':worker,'chief_call_id':chief,
                'worker_model_id':worker_model,'chief_model_id':chief_model,
                'owner_accepted_result':True})
    return {'campaign_id':campaign_id,'total_steps':30,'verified_completed_steps':completed,
            'verified_departments':len({entry['department'] for entry in entries}),
            'audit_type':'local_sqlite_model_call_and_owner_review',
            'independently_verified_gguf_binary':False,
            'physically_tested_windows_exe':False,
            'actual_external_sales_or_payments_confirmed':False,
            'steps':entries}


def _bytes(payload):
    return (json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')


def _folder(store):
    return Path(store.path).resolve().parent/'aiwack_company_evidence'


def export(store,campaign_id:int)->dict:
    store.require_permission('company:manage')
    if type(campaign_id) is not int or campaign_id<=0:
        raise ValueError('30업무 협업 번호 오류')
    payload=_build(store,campaign_id)
    body=_bytes(payload)
    digest=hashlib.sha256(body).hexdigest()
    folder=_folder(store)
    filename=f'campaign_{campaign_id}_{payload["verified_completed_steps"]}_{digest[:20]}.json'
    path=folder/filename
    committed=False
    written=False
    try:
        with store._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            initialize(con)
            if stopped(con):raise PermissionError('비상정지 중 감사 파일 생성 금지')
            if con.execute('''SELECT 1 FROM aiwack_campaign_evidence_exports
                WHERE campaign_id=? AND completed_count=?''',
                (campaign_id,payload['verified_completed_steps'])).fetchone():
                raise ValueError('동일 완료 단계의 원본 감사 파일이 이미 존재합니다.')
            folder.mkdir(parents=True,exist_ok=True)
            if folder.is_symlink() or path.is_symlink():
                raise ValueError('감사 폴더에 심볼릭 링크가 있습니다.')
            # Write exclusively; never overwrite another provenance archive.
            with path.open('xb') as output:
                output.write(body)
                output.flush()
                os.fsync(output.fileno())
            written=True
            export_id=int(con.execute('''INSERT INTO aiwack_campaign_evidence_exports
                (campaign_id,completed_count,filename,manifest_sha256)
                VALUES(?,?,?,?)''',
                (campaign_id,payload['verified_completed_steps'],filename,digest)).lastrowid)
        committed=True
        return read(store,export_id)
    except BaseException:
        if written and not committed:path.unlink(missing_ok=True)
        raise


def read(store,export_id:int):
    store.require_permission('company:manage')
    if type(export_id) is not int or export_id<=0:raise ValueError('감사 파일 번호 오류')
    with store._connect() as con:
        initialize(con)
        row=con.execute('''SELECT campaign_id,completed_count,filename,manifest_sha256
                    FROM aiwack_campaign_evidence_exports WHERE id=?''',(export_id,)).fetchone()
    if not row:raise ValueError('감사 파일 기록이 없습니다.')
    campaign,completed,name,digest=row
    payload=_build(store,campaign,upto=completed)
    body=_bytes(payload)
    folder=_folder(store)
    path=folder/name
    if (name!=f'campaign_{campaign}_{completed}_{digest[:20]}.json'
            or folder.is_symlink() or path.is_symlink() or not path.is_file()
            or hashlib.sha256(body).hexdigest()!=digest
            or path.stat().st_size != len(body) or path.read_bytes()!=body):
        raise ValueError('30업무 감사 원본 파일 또는 승인 체인이 변경됐습니다.')
    return {'id':export_id,'campaign_id':campaign,'completed_tasks':completed,
            'filename':str(path),'sha256':digest,
            'sqlite_audit_and_owner_review_verified':True,
            'independently_verified_gguf_binary':False,
            'physically_tested_windows_exe':False}


def inspect(store, campaign_id: int) -> dict:
    """관리자 확인용 30개 실제 모델/승인 단계 별 증빙 상태. DB 수정 금지."""
    store.require_permission('company:manage')
    if type(campaign_id) is not int or campaign_id<=0:
        raise ValueError('전체 협업 번호 오류')
    plan=wide.read(store,campaign_id)
    progress=wide.verified_progress(store,campaign_id)
    rows=[]
    with store._connect() as con:
        initialize(con)
        for step in plan['steps']:
            ordinal=step['ordinal']
            approval=wide._verified_step_evidence(con,campaign_id,ordinal,
                                  expected_chief=plan['chief_employee_id']) is not None
            chief=bool(approval and wide._verified_chief_model_call_link(
                   con,campaign_id,ordinal,expected_chief=plan['chief_employee_id']))
            rows.append({'ordinal':ordinal,'department':step['department'],
                         'employee_id':step['employee_id'],'task_id':step['task_id'],
                         'owner_review_and_worker_call_valid':approval,
                         'chief_model_report_call_valid':chief,
                         'ready_for_handoff':approval and chief})
    return {'campaign_id':campaign_id,'total_tasks':len(rows),
            'approved_worker_steps':sum(s['owner_review_and_worker_call_valid'] for s in rows),
            'chief_call_linked_steps':sum(s['chief_model_report_call_valid'] for s in rows),
            'verified_sequential_steps':progress['verified_genuine_prefix_tasks'],
            'all_30_genuine_model_audits_and_owner_reviews_verified':(
                len(rows)==30 and progress['verified_genuine_prefix_tasks']==30),
            'rows':rows,'independent_model_execution_or_binary_verified':False,
            'physical_windows_exe_verified':False}



def inspect_disk_consistency(store, limit: int = 100) -> dict:
    """읽기 전용 30업무 호출 감사 파일/SQLite 중단 복구 목록.

    정상/손상/미등록/위험 경로를 구분한다. 파일 삭제·복구·승인·모델
    실행은 수행하지 않는다. 범위를 넘긴 경우 전체 무결성 통과를 주장하지 않는다.
    """
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('호출 감사 파일 점검 한도는 1~1000 정수여야 합니다.')
    folder = _folder(store)
    if folder.is_symlink():
        raise ValueError('호출 감사 폴더가 심볼릭 링크여서 안전하게 점검할 수 없습니다.')
    with store._connect() as con:
        initialize(con)
        total = con.execute(
            'SELECT COUNT(*) FROM aiwack_campaign_evidence_exports'
        ).fetchone()[0]
        rows = con.execute(
            '''SELECT id,filename FROM aiwack_campaign_evidence_exports
               ORDER BY id LIMIT ?''', (limit,)
        ).fetchall()

    verified, damaged = [], []
    for ident, name in rows:
        try:
            if (not isinstance(name, str) or not re.fullmatch(
                    r'campaign_[1-9][0-9]*_(?:[1-9]|[12][0-9]|30)_[0-9a-f]{20}\.json',
                    name)):
                raise ValueError('등록된 호출 감사 파일 이름이 올바르지 않습니다.')
            proof = read(store, int(ident))
        except (ValueError, PermissionError, OSError, sqlite3.Error) as exc:
            damaged.append({'id': int(ident), 'filename': name,
                            'error_type': type(exc).__name__,
                            'reason': str(exc)[:240]})
        else:
            verified.append({'id': int(ident), 'filename': name,
                             'sha256': proof['sha256']})

    orphans, unsafe = [], []
    scanned = 0
    truncated_files = False
    if folder.exists():
        with os.scandir(folder) as entries, store._connect() as con:
            for entry in entries:
                name = entry.name
                if not (name.startswith('campaign_') and name.endswith('.json')):
                    continue
                if scanned >= limit:
                    truncated_files = True
                    break
                scanned += 1
                if (entry.is_symlink() or not entry.is_file(follow_symlinks=False)
                        or not re.fullmatch(
                            r'campaign_[1-9][0-9]*_(?:[1-9]|[12][0-9]|30)_[0-9a-f]{20}\.json',
                            name)):
                    unsafe.append(name)
                elif con.execute(
                    'SELECT 1 FROM aiwack_campaign_evidence_exports WHERE filename=?',
                    (name,)
                ).fetchone() is None:
                    orphans.append(name)

    complete = total <= limit and not truncated_files
    return {
        'format': 'AIWACK_CAMPAIGN_EVIDENCE_CRASH_INVENTORY_V1',
        'registered_rows_scanned': len(rows),
        'registered_rows_total': total,
        'candidate_files_scanned': scanned,
        'registered_files_verified': verified,
        'registered_files_failed': damaged,
        'orphaned_unregistered_files': sorted(orphans),
        'unsafe_candidate_paths': sorted(unsafe),
        'scan_complete': complete,
        'all_scanned_registered_files_intact': not damaged,
        'no_orphaned_files_confirmed': complete and not orphans and not unsafe,
        'requires_owner_review': bool(damaged or orphans or unsafe or not complete),
        'files_deleted': False,
        'automatic_recovery_performed': False,
        'external_actions_executed': False,
        'physical_windows_10_11_recovery_verified': False,
        'uninterrupted_24h_operation_verified': False,
    }
