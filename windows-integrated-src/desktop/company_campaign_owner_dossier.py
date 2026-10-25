"""관리자 최종 승인된 30업무 전체의 실제 모델 감사·보고서 로컬 인계 패키지.

원본 AIWACK 네이티브 Windows/Tk/SQLite 프로젝트용 추가 모듈.
기존 회사 협업과 모델 호출·직원 결과 승인·총괄 최종보고를 새로 모의하지 않는다.
외부 전송·결제·게시·송금·모델 재호출은 하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from uuid import uuid4

from desktop import company_campaign_evidence as evidence
from desktop import company_campaign_final_report as final
from desktop import company_campaign_plan_provenance as provenance
from desktop.stage87_90_management import stopped

MAX_DOSSIER_BYTES = 1024 * 1024


def initialize(con) -> None:
    final.initialize(con)
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_campaign_owner_dossiers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL REFERENCES aiwack_wide_campaigns(id),
        report_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_campaign_final_reports(id),
        final_report_sha256 TEXT NOT NULL CHECK(length(final_report_sha256)=64),
        evidence_sha256 TEXT NOT NULL CHECK(length(evidence_sha256)=64),
        filename TEXT NOT NULL UNIQUE,
        file_sha256 TEXT NOT NULL CHECK(length(file_sha256)=64),
        byte_count INTEGER NOT NULL CHECK(byte_count BETWEEN 1 AND 1048576),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    for action in ('UPDATE', 'DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS aiwack_owner_dossier_no_{action.lower()}
            BEFORE {action} ON aiwack_campaign_owner_dossiers BEGIN
            SELECT RAISE(ABORT,'관리자 최종 결과 인계 감사 변경·삭제 금지'); END''')


def _folder(store) -> Path:
    return Path(store.path).resolve().parent / 'aiwack_approved_final_dossiers'


def _content(store, con, report_id: int) -> tuple[dict, bytes]:
    """Build from verified original model calls, not text inferred from a prompt."""
    record = final._checked_row(store, con, report_id)
    if record['decision'] != 'accepted':
        raise PermissionError('총괄 최종 보고의 관리자 승인이 필요합니다.')
    # Merge the preserved 19:36 five-group genuine chief-call provenance with
    # the 17:35 owner-approved final handoff. Both proofs are recomputed from
    # the original SQLite calls; no prompt text or fabricated model output.
    plan = provenance.snapshot(store, int(record['campaign_id']))
    if (plan['plan_state'] != 'approved'
            or plan['verified_plan_groups'] != 5
            or plan['verified_departments'] != 15
            or not 5 <= plan['verified_chief_call_count'] <= 15
            or plan['campaign_id'] != record['campaign_id']):
        raise ValueError('총괄 5그룹 실제 모델 계획과 관리자 승인 원본이 불일치합니다.')
    manifest = evidence._build(store, int(record['campaign_id']), upto=30)
    if (manifest['verified_completed_steps'] != 30
            or manifest['verified_departments'] != 15
            or len(manifest['steps']) != 30):
        raise ValueError('15부서 30업무 실제 모델·승인 원본이 모두 필요합니다.')
    if manifest['independently_verified_gguf_binary']:
        raise ValueError('로컬 호출 감사로 GGUF 바이너리 검증을 주장할 수 없습니다.')
    payload = {
        'format': 'AIWACK_OWNER_APPROVED_FINAL_DOSSIER_V1',
        'campaign_id': int(record['campaign_id']),
        'final_report_id': int(report_id),
        'chief_employee_id': int(record['chief_employee_id']),
        'chief_model_call_id': int(record['chief_model_call_id']),
        'final_report': record['report'],
        'final_report_sha256': record['report_sha256'],
        'source_evidence_sha256': record['evidence_sha256'],
        'owner_final_decision': 'accepted',
        'owner_final_decision_reason': record['decision_reason'],
        'chief_five_group_plan': plan,
        'chief_five_group_plan_sha256': plan['snapshot_sha256'],
        'manifest': manifest,
        'physical_windows_10_11_exe_verified': False,
        'independent_real_gguf_binary_attested': False,
        'real_external_pg_or_bank_settlement_verified': False,
        'externally_published_or_sent': False,
    }
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    if not 1 <= len(raw) <= MAX_DOSSIER_BYTES:
        raise ValueError('관리자 인계 패키지 크기는 1MiB 이하여야 합니다.')
    return record, raw


def export(store, report_id: int) -> dict:
    """Only explicit owner action writes a local immutable file and SQLite audit."""
    store.require_permission('company:manage')
    if type(report_id) is not int or report_id <= 0:
        raise ValueError('최종 보고 ID 오류')
    folder = _folder(store)
    if folder.is_symlink():
        raise ValueError('심볼릭 링크 경로에는 관리자 인계 파일을 생성할 수 없습니다.')
    filename = 'owner_final_' + uuid4().hex + '.json'
    target = folder / filename
    written = False
    committed = False
    try:
        with store._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            initialize(con)
            if stopped(con):
                raise PermissionError('비상정지 중 최종 인계 파일을 만들 수 없습니다.')
            if con.execute('SELECT 1 FROM aiwack_campaign_owner_dossiers WHERE report_id=?',
                           (report_id,)).fetchone():
                raise ValueError('이 최종 보고의 관리자 인계 파일이 이미 존재합니다.')
            record, raw = _content(store, con, report_id)
            folder.mkdir(parents=True, exist_ok=True)
            if folder.is_symlink() or target.is_symlink():
                raise ValueError('심볼릭 링크 경로는 허용하지 않습니다.')
            with target.open('xb') as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            written = True
            digest = hashlib.sha256(raw).hexdigest()
            ident = int(con.execute('''INSERT INTO aiwack_campaign_owner_dossiers
                (campaign_id,report_id,final_report_sha256,evidence_sha256,
                 filename,file_sha256,byte_count) VALUES(?,?,?,?,?,?,?)''',
                (record['campaign_id'],report_id,record['report_sha256'],
                 record['evidence_sha256'],filename,digest,len(raw))).lastrowid)
        committed = True
        return read(store, ident)
    except BaseException:
        if written and not committed:
            target.unlink(missing_ok=True)
        raise


def read(store, dossier_id: int) -> dict:
    """Verify both persisted SQLite provenance and exact exported bytes."""
    store.require_permission('company:manage')
    if type(dossier_id) is not int or dossier_id <= 0:
        raise ValueError('관리자 인계 번호 오류')
    with store._connect() as con:
        initialize(con)
        row = con.execute('''SELECT campaign_id,report_id,final_report_sha256,
            evidence_sha256,filename,file_sha256,byte_count
            FROM aiwack_campaign_owner_dossiers WHERE id=?''', (dossier_id,)).fetchone()
        if row is None:
            raise ValueError('최종 인계 기록이 없습니다.')
        campaign_id, report_id, report_sha, evidence_sha, filename, digest, size = row
        record, expected = _content(store, con, int(report_id))
        if (record['campaign_id'] != campaign_id
                or record['report_sha256'] != report_sha
                or record['evidence_sha256'] != evidence_sha):
            raise ValueError('관리자 최종 보고와 인계 감사가 불일치합니다.')
    if (not isinstance(filename, str) or not filename.startswith('owner_final_')
            or not filename.endswith('.json') or len(filename) != len('owner_final_') + 32 + len('.json')
            or any(ch not in '0123456789abcdef' for ch in filename[12:-5])):
        raise ValueError('최종 인계 파일 이름 형식 오류')
    folder = _folder(store)
    path = folder / filename
    if folder.is_symlink() or path.is_symlink() or not path.is_file():
        raise ValueError('최종 인계 원본 파일이 없거나 안전하지 않은 경로입니다.')
    if path.stat().st_size != size or size > MAX_DOSSIER_BYTES:
        raise ValueError('최종 인계 원본 파일 크기가 변경됐습니다.')
    raw = path.read_bytes()
    if (hashlib.sha256(raw).hexdigest() != digest or raw != expected):
        raise ValueError('최종 인계 원본 파일 SHA256·내용 무결성 오류')
    return {'id': dossier_id, 'campaign_id': campaign_id,
            'final_report_id': report_id, 'path': str(path),
            'file_sha256': digest, 'byte_count': size,
            'owner_final_approved': True,
            'verified_chief_plan_groups': 5,
            'verified_approved_employee_steps': 30,
            'independent_gguf_binary_verified': False,
            'actual_windows_10_11_gui_verified': False,
            'external_payment_or_publication_executed': False}


def list_exports(store, limit: int = 30) -> list[dict]:
    """Return previously approved local dossiers with byte-level integrity proof.

    A changed/missing file remains visible as an error, never as an approved
    delivery. This operation does not create files, call a model, or publish.
    """
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('최종 인계 감사 조회 범위는 1~100건이어야 합니다.')
    with store._connect() as con:
        initialize(con)
        ids = [int(row[0]) for row in con.execute("SELECT id FROM aiwack_campaign_owner_dossiers ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
    return [read(store, dossier_id) for dossier_id in ids]


def find_by_campaign(store, campaign_id: int) -> dict | None:
    """Return an existing owner-approved dossier with a full integrity recheck.

    This read-only operation never calls a model, publishes, or auto-approves.
    """
    store.require_permission('company:manage')
    if type(campaign_id) is not int or campaign_id <= 0:
        raise ValueError('회사 전체 협업 번호는 양의 정수여야 합니다.')
    with store._connect() as con:
        initialize(con)
        row = con.execute('''SELECT id FROM aiwack_campaign_owner_dossiers
            WHERE campaign_id=? ORDER BY id DESC LIMIT 1''', (campaign_id,)).fetchone()
    return read(store, int(row[0])) if row is not None else None


def inspect_export_history(store, limit: int = 30) -> list[dict]:
    """모든 인계의 상태를 각각 검증하고 손상된 기록도 실패로 표시한다.

    기존 list_exports의 엄격한 예외 동작을 변경하지 않는다. 이 함수는
    운영자가 정상 기록과 손상된 기록을 함께 확인하는 읽기 전용 감사이다.
    """
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('최종 인계 감사 조회 범위는 1~100건이어야 합니다.')
    with store._connect() as con:
        initialize(con)
        rows = con.execute("""SELECT id,campaign_id,report_id,file_sha256
            FROM aiwack_campaign_owner_dossiers ORDER BY id DESC LIMIT ?""",
            (limit,)).fetchall()
    result = []
    for dossier_id, campaign_id, report_id, expected_sha in rows:
        try:
            verified = read(store, int(dossier_id))
        except (ValueError, PermissionError, OSError, sqlite3.Error) as exc:
            result.append({'id': dossier_id, 'campaign_id': campaign_id,
                           'final_report_id': report_id,
                           'stored_file_sha256': expected_sha,
                           'integrity': 'failed',
                           'error_type': type(exc).__name__,
                           'reason': str(exc)[:300]})
        else:
            result.append({'id': dossier_id, 'campaign_id': campaign_id,
                           'final_report_id': report_id,
                           'file_sha256': verified['file_sha256'],
                           'integrity': 'verified',
                           'owner_final_approved': verified['owner_final_approved'],
                           'independent_gguf_binary_verified': False})
    return result


def inspect_disk_consistency(store, limit: int = 100) -> dict:
    """읽기 전용 관리자 인계 디스크/SQLite 불일치 전수 분류.

    등록 레코드 감사와 폴더 파일 감사를 독립적으로 제한한다. 폴더의
    비대상 파일은 조회 한도를 소모하지 않으며, 감사 한도를 넘긴
    등록 파일을 미등록 고아 파일로 오판하지 않는다.
    """
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('인계 디스크 감사 조회 한도는 1~1000건이어야 합니다.')
    folder = _folder(store)
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise ValueError('관리자 인계 폴더가 안전한 일반 디렉터리가 아닙니다.')
    with store._connect() as con:
        initialize(con)
        # 미검사 등록 파일도 전체 등록 이름에 포함하여 고아 파일 오판 방지.
        rows = con.execute('''SELECT id,filename FROM aiwack_campaign_owner_dossiers
            ORDER BY id''').fetchall()
    registered_names = {name for _, name in rows}
    registered = {name: int(ident) for ident, name in rows[:limit]}
    truncated_records = len(rows) > limit
    verified, damaged = [], []
    for name, ident in registered.items():
        try:
            proof = read(store, ident)
        except (ValueError, PermissionError, OSError, sqlite3.Error) as exc:
            damaged.append({'id': ident, 'filename': name,
                            'error_type': type(exc).__name__,
                            'reason': str(exc)[:240]})
        else:
            verified.append({'id': ident, 'filename': name,
                             'sha256': proof['file_sha256']})
    orphans, unsafe = [], []
    truncated_files = False
    scanned_candidates = 0
    if folder.exists():
        with os.scandir(folder) as iterator:
            for entry in iterator:
                name = entry.name
                if not re.fullmatch(r'owner_final_[0-9a-f]{32}\.json', name):
                    continue
                if scanned_candidates >= limit:
                    truncated_files = True
                    break
                scanned_candidates += 1
                if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                    unsafe.append(name)
                elif name not in registered_names:
                    orphans.append(name)
    complete = not truncated_records and not truncated_files
    return {
        'format': 'AIWACK_OWNER_DOSSIER_CRASH_INVENTORY_V1',
        'registered_rows_scanned': len(registered),
        'registered_rows_total': len(rows),
        'candidate_files_scanned': scanned_candidates,
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


def inspect_disk_consistency_full(store, max_records: int = 10000) -> dict:
    """관리자 최종 인계 등록/디스크를 제한 범위 안에서 전체 재검사."""
    from desktop.company_disk_audit_full import inspect_full
    with store._connect() as con:
        initialize(con)
    return inspect_full(
        store, folder=_folder(store), table='aiwack_campaign_owner_dossiers',
        filename_pattern=r'owner_final_[0-9a-f]{32}\.json',
        candidate_prefix='owner_final_', verify=read, max_records=max_records)
