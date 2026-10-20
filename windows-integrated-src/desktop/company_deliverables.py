"""Actual local approved-result delivery and deterministic quality reports.

Writes markdown deliverables ONLY into the owner's own AIWACK data directory.
No network, publishing, payment, executing model-generated code or fake quality
approval. Every output is bound to a reviewed SQLite artifact and SHA256 hash.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re

from desktop.storage import user_data_dir


def check_quality(store, artifact_id: int) -> dict:
    """Checks mechanical integrity, NOT the truth or suitability of AI output."""
    store.require_permission('company:manage')
    artifact=store.read_task_artifact(artifact_id)
    body=artifact['body']
    actual=hashlib.sha256(body.encode('utf-8')).hexdigest()
    warnings=[]
    if actual != artifact['sha256']:
        warnings.append('저장된 결과물의 SHA256 무결성이 일치하지 않습니다.')
    if len(body.strip()) < 80:
        warnings.append('본문이 80자 미만이므로 내용 검토가 필요합니다.')
    if '\x00' in body or any(ord(c)<9 for c in body):
        warnings.append('본문에 허용되지 않는 제어 문자가 있습니다.')
    if re.search(r'(?i)(?:TODO|FIXME|PLACEHOLDER|여기에\s*(?:작성|입력)|미작성)',body):
        warnings.append('미작성 또는 임시 내용으로 보이는 표현이 있습니다.')
    dupes=[a['id'] for a in store.list_task_artifacts()
           if int(a['id'])!=artifact_id and a['sha256']==actual]
    if dupes:
        warnings.append('동일 SHA256의 다른 저장된 결과물이 있습니다.')
    return {'artifact_id':artifact_id,'integrity_ok':actual==artifact['sha256'],
            'body_chars':len(body),'review_status':artifact['review_status'],
            'duplicate_ids':dupes[:20],'warnings':warnings,
            'machine_checks_only':True,'automatically_approved':False}


def _exports_dir(base: Path | None = None) -> Path:
    root=(Path(base) if base is not None else user_data_dir()).expanduser().resolve()
    target=root/'approved_deliverables'
    if target.is_symlink():
        raise PermissionError('내보내기 폴더가 외부 연결을 가리켜 저장을 거부합니다.')
    target.mkdir(parents=True,exist_ok=True)
    if target.resolve()!=root.joinpath('approved_deliverables').resolve():
        raise PermissionError('내보내기 폴더가 변경됐습니다.')
    return target


def initialize(store) -> None:
    store.require_permission('company:manage')
    with store._connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS aiwack_deliverable_exports(
            artifact_id INTEGER PRIMARY KEY REFERENCES company_task_artifacts(id),
            file_name TEXT NOT NULL UNIQUE,
            sha256 TEXT NOT NULL CHECK(length(sha256)=64),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")


def export_approved(store, artifact_id: int, *, root: Path | None = None) -> dict:
    """Owner-click-only export; the generated result is never auto-published."""
    store.require_permission('company:manage')
    if type(artifact_id) is not int or artifact_id <= 0:
        raise ValueError('결과물 번호는 양의 정수여야 합니다.')
    initialize(store)
    quality=check_quality(store,artifact_id)
    if not quality['integrity_ok']:
        raise ValueError('결과물 데이터 무결성이 확인되지 않아 저장할 수 없습니다.')
    if quality['review_status']!='approved':
        raise PermissionError('소유자가 승인한 결과물만 파일로 내보낼 수 있습니다.')
    artifact=store.read_task_artifact(artifact_id)
    # Fixed, predictable file names. Do NOT use LLM-generated titles as paths.
    file_name=f"approved_artifact_{artifact_id:06d}_{artifact['sha256'][:12]}.md"
    body=f"# {artifact['title']}\n\n{artifact['body']}\n"
    digest=hashlib.sha256(body.encode('utf-8')).hexdigest()
    folder=_exports_dir(root)
    output=folder/file_name
    if output.is_symlink():
        raise PermissionError('내보내기 결과물이 외부 경로를 가리킵니다.')
    if output.exists():
        previous=output.read_bytes()
        if hashlib.sha256(previous).hexdigest()!=digest:
            raise FileExistsError('기존에 내보낸 파일이 변경됐습니다. 덮어쓰지 않습니다.')
    else:
        data=body.encode('utf-8')
        flags=os.O_CREAT|os.O_EXCL|os.O_WRONLY
        if hasattr(os,'O_BINARY'):
            flags |= os.O_BINARY
        fd=os.open(output,flags,0o600)
        try:
            with os.fdopen(fd,'wb') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            output.unlink(missing_ok=True)
            raise
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        record=con.execute('SELECT file_name,sha256 FROM aiwack_deliverable_exports WHERE artifact_id=?',
                           (artifact_id,)).fetchone()
        if record is None:
            con.execute('INSERT INTO aiwack_deliverable_exports(artifact_id,file_name,sha256) VALUES(?,?,?)',
                        (artifact_id,file_name,digest))
        elif tuple(record)!=(file_name,digest):
            raise RuntimeError('기존 결과물 내보내기 감사 기록과 파일이 일치하지 않습니다.')
    return {'artifact_id':artifact_id,'path':str(output),
            'sha256':digest,'owner_approved':True,'published_externally':False}


def verify_exports(store, *, root: Path | None = None) -> list[dict]:
    store.require_permission('company:manage')
    initialize(store)
    folder=_exports_dir(root)
    with store._connect() as con:
        records=con.execute('SELECT artifact_id,file_name,sha256 FROM aiwack_deliverable_exports ORDER BY artifact_id').fetchall()
    report=[]
    for artifact_id,name,digest in records:
        path=folder/name
        valid=(not path.is_symlink() and path.is_file() and
               hashlib.sha256(path.read_bytes()).hexdigest()==digest)
        report.append({'artifact_id':int(artifact_id),'file_name':name,
                       'integrity_ok':bool(valid)})
    return report
