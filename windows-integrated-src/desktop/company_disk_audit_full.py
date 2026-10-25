"""기존 Windows AIWACK 호출 감사/관리자 인계 파일의 범위 명시형 전체 점검.

모든 결과는 읽기 전용 SQLite/디스크 재검사이다. 실제 GGUF 바이너리,
Windows GUI, 외부 거래나 24시간 운영 성공을 증명하지 않는다.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path


def inspect_full(store, *, folder: Path, table: str, filename_pattern: str,
                 candidate_prefix: str, verify, max_records: int = 10000) -> dict:
    """상한 내 등록 기록과 후보 파일을 각각 검사하며 불완전한 범위를 표시한다.

    table/pattern/prefix는 외부 입력이 아니라 각 기존 모듈의 고정 상수만
    전달한다. 파일을 수정·삭제·자동 복구하지 않는다.
    """
    store.require_permission('company:manage')
    if type(max_records) is not int or not 1 <= max_records <= 10000:
        raise ValueError('전체 파일 감사 한도는 1~10000 정수여야 합니다.')
    if table not in ('aiwack_campaign_evidence_exports',
                     'aiwack_campaign_owner_dossiers'):
        raise ValueError('허용되지 않은 로컬 감사 테이블입니다.')
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise ValueError('감사 폴더가 안전한 일반 디렉터리가 아닙니다.')

    with store._connect() as con:
        total = con.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
        rows = con.execute('SELECT id,filename FROM ' + table +
                           ' ORDER BY id LIMIT ?', (max_records,)).fetchall()
    partial_rows = total > len(rows)
    registered_names = {name for _, name in rows if isinstance(name, str)}
    verified, failed = [], []
    for ident, name in rows:
        try:
            if (type(ident) is not int or ident <= 0
                    or not isinstance(name, str)
                    or not re.fullmatch(filename_pattern, name)):
                raise ValueError('등록된 감사 원본의 번호 또는 파일 이름 오류')
            proof = verify(store, ident)
            digest = proof.get('sha256', proof.get('file_sha256'))
            if (not isinstance(digest, str) or
                    re.fullmatch(r'[0-9a-f]{64}', digest) is None):
                raise ValueError('등록된 감사 파일의 SHA256 검증 결과 오류')
        except (ValueError, PermissionError, OSError, sqlite3.Error) as exc:
            failed.append({'id': ident, 'filename': name,
                           'error_type': type(exc).__name__,
                           'reason': str(exc)[:240]})
        else:
            verified.append({'id': ident, 'filename': name, 'sha256': digest})

    orphans, unsafe, unknown = [], [], []
    candidates = 0
    partial_files = False
    if folder.exists():
        with os.scandir(folder) as entries:
            for entry in entries:
                name = entry.name
                if not (name.startswith(candidate_prefix) and name.endswith('.json')):
                    continue
                if candidates >= max_records:
                    partial_files = True
                    break
                candidates += 1
                if (entry.is_symlink() or not entry.is_file(follow_symlinks=False)
                        or re.fullmatch(filename_pattern, name) is None):
                    unsafe.append(name)
                elif name not in registered_names:
                    # 등록 행 일부만 읽었다면 미확인 파일을 고아로 단정하지 않는다.
                    (unknown if partial_rows else orphans).append(name)

    complete = not partial_rows and not partial_files
    review = bool(failed or orphans or unsafe or unknown or not complete)
    return {
        'format': 'AIWACK_LOCAL_FULL_DISK_INVENTORY_V1',
        'audit_table': table,
        'registered_rows_total': total,
        'registered_rows_scanned': len(rows),
        'candidate_files_scanned': candidates,
        'registered_files_verified': verified,
        'registered_files_failed': failed,
        'orphaned_unregistered_files': sorted(orphans),
        'unsafe_candidate_paths': sorted(unsafe),
        'unclassified_candidate_files': sorted(unknown),
        'scan_complete': complete,
        'all_registered_files_verified': complete and len(verified) == total
                                         and not failed and not orphans and not unsafe,
        'requires_owner_review': review,
        'files_deleted': False,
        'automatic_recovery_performed': False,
        'external_actions_executed': False,
        'independent_gguf_binary_verified': False,
        'physical_windows_10_11_gui_verified': False,
        'uninterrupted_24h_operation_verified': False,
        'final_T01_T20_acceptance_passed': False,
    }
