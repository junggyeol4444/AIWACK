"""기존 Windows AIWACK 호출 감사/관리자 인계 파일의 범위 명시형 전체 점검.

모든 결과는 읽기 전용 SQLite/디스크 재검사이다. 실제 GGUF 바이너리,
Windows GUI, 외부 거래나 24시간 운영 성공을 증명하지 않는다.
"""
from __future__ import annotations

import hashlib
import hmac
import json
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
    folder_before = folder.stat() if folder.exists() else None
    verified, failed = [], []
    seen_names = set()
    for ident, name in rows:
        try:
            if (type(ident) is not int or ident <= 0
                    or not isinstance(name, str)
                    or not re.fullmatch(filename_pattern, name)):
                raise ValueError('등록된 감사 원본의 번호 또는 파일 이름 오류')
            if name in seen_names:
                raise ValueError('서로 다른 등록 번호가 동일한 감사 파일을 참조합니다.')
            seen_names.add(name)
            proof = verify(store, ident)
            if not isinstance(proof, dict) or type(proof.get('id')) is not int or proof['id'] != ident:
                raise ValueError('감사 검증 결과가 등록 번호와 일치하지 않습니다.')
            proof_path = (proof.get('filename') if table == 'aiwack_campaign_evidence_exports'
                          else proof.get('path'))
            # The verifier must point to this exact local archive, not merely
            # another directory containing a file with the same basename.
            expected_path = folder / name
            if (not isinstance(proof_path, str)
                    or not Path(proof_path).is_absolute()
                    or Path(proof_path) != expected_path):
                raise ValueError('감사 검증 결과의 파일 경로가 등록 원본과 일치하지 않습니다.')
            if expected_path.is_symlink() or not expected_path.is_file():
                raise ValueError('등록된 감사 파일이 없거나 안전한 일반 파일이 아닙니다.')
            digest = proof.get('sha256', proof.get('file_sha256'))
            if (not isinstance(digest, str) or
                    re.fullmatch(r'[0-9a-f]{64}', digest) is None):
                raise ValueError('등록된 감사 파일의 SHA256 검증 결과 오류')
            # Rehash the actual archive independently of the verifier. A
            # matching ID/path and a syntactically valid digest are not proof.
            before = expected_path.stat()
            if not 0 < before.st_size <= 16 * 1024 * 1024:
                raise ValueError('감사 원본 파일 크기가 허용 범위를 벗어났습니다.')
            actual = hashlib.sha256()
            counted = 0
            with expected_path.open('rb') as source:
                for chunk in iter(lambda: source.read(65536), b''):
                    counted += len(chunk)
                    if counted > 16 * 1024 * 1024:
                        raise ValueError('감사 원본 파일이 점검 도중 허용 크기를 넘었습니다.')
                    actual.update(chunk)
            after = expected_path.stat()
            if (counted != before.st_size or before.st_size != after.st_size
                    or before.st_mtime_ns != after.st_mtime_ns
                    or before.st_ino != after.st_ino
                    or expected_path.is_symlink()):
                raise ValueError('감사 원본 파일이 점검 도중 변경됐습니다.')
            if not hmac.compare_digest(actual.hexdigest(), digest):
                raise ValueError('디스크 감사 원본 SHA256이 등록된 검증 결과와 다릅니다.')
        except (ValueError, PermissionError, OSError, sqlite3.Error,
                TypeError, KeyError) as exc:
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
                if not name.startswith(candidate_prefix):
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

    folder_after = folder.stat() if folder.exists() else None
    folder_changed = (folder_before is None) != (folder_after is None)
    if folder_before is not None and folder_after is not None:
        folder_changed = (folder_before.st_mtime_ns != folder_after.st_mtime_ns
                          or folder_before.st_ino != folder_after.st_ino)
    complete = not partial_rows and not partial_files and not folder_changed
    review = bool(failed or orphans or unsafe or unknown or not complete)
    # 조회 결과의 결정적 지문일 뿐, 전자서명이나 외부 모델 실행 증명이 아니다.
    inventory = {
        'table': table, 'registered_rows_total': total,
        'registered_rows_scanned': len(rows), 'candidate_files_scanned': candidates,
        'verified': verified, 'failed': failed,
        'orphaned': sorted(orphans), 'unsafe': sorted(unsafe),
        'unclassified': sorted(unknown), 'scan_complete': complete,
        'directory_changed_during_scan': folder_changed,
    }
    inventory_sha256 = hashlib.sha256(json.dumps(
        inventory, ensure_ascii=False, sort_keys=True, separators=(',', ':')
    ).encode('utf-8')).hexdigest()
    return {
        'format': 'AIWACK_LOCAL_FULL_DISK_INVENTORY_V1',
        'audit_table': table,
        'inventory_snapshot_sha256': inventory_sha256,
        'inventory_snapshot_is_signature': False,
        'registered_rows_total': total,
        'registered_rows_scanned': len(rows),
        'candidate_files_scanned': candidates,
        'registered_files_verified': verified,
        'registered_files_failed': failed,
        'orphaned_unregistered_files': sorted(orphans),
        'unsafe_candidate_paths': sorted(unsafe),
        'unclassified_candidate_files': sorted(unknown),
        'scan_complete': complete,
        'directory_changed_during_scan': folder_changed,
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
