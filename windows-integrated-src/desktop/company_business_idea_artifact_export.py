"""관리자 승인된 실제 GGUF 조사·상품 결과를 로컬 파일로만 보존한다.

기존 SQLite·한국어 Tk·Windows EXE의 보존형 확장이다.
모델 결과는 검증된 시장 수요, 완성된 판매 상품 또는 매출이 아니다.
외부 전송·게시·결제·고객 연락은 절대 실행하지 않는다.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

from desktop.company_business_idea_pipeline import _digest, _id
from desktop.company_business_idea_delivery import (
    initialize as initialize_delivery, _verified_links, _handoff, _approved_artifact,
)
from desktop.stage87_90_management import stopped

MAX_EXPORT_BYTES = 160 * 1024
_FILENAME_PREFIX = 'idea_'


def initialize(con: sqlite3.Connection) -> None:
    initialize_delivery(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_idea_local_product_exports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        idea_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_chief_business_ideas(id),
        business_id INTEGER NOT NULL REFERENCES managed_businesses(id),
        catalog_id INTEGER NOT NULL REFERENCES local_catalog_items(id),
        review_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_idea_delivery_reviews(id),
        research_artifact_id INTEGER NOT NULL REFERENCES company_task_artifacts(id),
        product_artifact_id INTEGER NOT NULL REFERENCES company_task_artifacts(id),
        filename TEXT NOT NULL UNIQUE,
        file_sha256 TEXT NOT NULL CHECK(length(file_sha256)=64),
        byte_count INTEGER NOT NULL CHECK(byte_count BETWEEN 1 AND 163840),
        receipt_sha256 TEXT NOT NULL CHECK(length(receipt_sha256)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    for operation in ('UPDATE', 'DELETE'):
        con.execute(f"""CREATE TRIGGER IF NOT EXISTS aiwack_idea_local_product_exports_no_{operation.lower()}
            BEFORE {operation} ON aiwack_idea_local_product_exports BEGIN
            SELECT RAISE(ABORT,'실제 GGUF 로컬 상품 결과물 원본 변경 금지'); END""")


def _folder(store) -> Path:
    return Path(store.path).resolve().parent / 'aiwack_idea_product_exports'


def _verified_content(con: sqlite3.Connection, idea_id: int) -> tuple[dict, bytes]:
    linked = _verified_links(con, idea_id)
    handoff = _handoff(con, idea_id, linked)
    row = con.execute("""SELECT id,idea_id,research_artifact_id,product_artifact_id,
        research_artifact_sha256,product_artifact_sha256,
        research_model_call_id,product_model_call_id,owner_note,receipt_sha256
        FROM aiwack_idea_delivery_reviews WHERE idea_id=?""", (idea_id,)).fetchone()
    if row is None:
        raise PermissionError('관리자가 승인한 조사·제작 2건의 내부 검토가 필요합니다.')
    (review_id,recorded_idea,research_id,product_id,research_sha,product_sha,
     research_call,product_call,note,receipt) = row
    payload = dict(idea_id=recorded_idea,research_artifact_id=research_id,
                   product_artifact_id=product_id,
                   research_artifact_sha256=research_sha,
                   product_artifact_sha256=product_sha,
                   research_model_call_id=research_call,
                   product_model_call_id=product_call,owner_note=note)
    if _digest(payload) != receipt or recorded_idea != idea_id:
        raise ValueError('내부 검토 감사 원본 SHA 불일치')
    for task_key,artifact_id,expected_sha,expected_call in (
        ('research_task_id',research_id,research_sha,research_call),
        ('product_task_id',product_id,product_sha,product_call),
    ):
        proof = _approved_artifact(con, handoff[task_key], int(artifact_id))
        if (proof['artifact_sha256'],proof['model_call_id']) != (expected_sha,expected_call):
            raise ValueError('직원 실제 모델 호출·승인 결과물 원본 불일치')
    source = con.execute("""SELECT
        r.title,r.body,p.title,p.body
        FROM company_task_artifacts r
        JOIN company_task_artifacts p ON p.id=?
        WHERE r.id=?""", (product_id,research_id)).fetchone()
    if source is None or any(type(v) is not str for v in source):
        raise ValueError('조사·제작 승인 결과물 본문이 없습니다.')
    research_title,research_body,product_title,product_body=source
    # 모델 본문을 가공·생성하지 않고 저장된 원문 그대로 보존한다.
    content = ('# 실제 GGUF 직원 결과물 · 관리자 내부 검토본\n\n'
        '주의: 이 문서는 실제 매출·시장 수요·상품 출시·외부 게시 증빙이 아닙니다.\n\n'
        f'사업 가설 번호: {idea_id}\n'
        f'사업 번호: {linked["business_id"]}\n'
        f'프로젝트 번호: {linked["project_id"]}\n'
        f'카탈로그 번호: {linked["catalog_id"]}\n'
        f'총괄 실제 모델 호출 번호: {linked["model_call_id"]}\n'
        f'총괄 모델 출력 SHA256: {linked["model_output_sha256"]}\n'
        f'관리자 내부 검토 번호: {review_id}\n'
        f'관리자 검토 원본 SHA256: {receipt}\n\n'
        f'## 조사 결과 #{research_id}: {research_title}\n'
        f'실제 직원 호출 번호: {research_call}\n'
        f'원문 SHA256: {research_sha}\n\n{research_body}\n\n'
        f'## 상품 제작 결과 #{product_id}: {product_title}\n'
        f'실제 직원 호출 번호: {product_call}\n'
        f'원문 SHA256: {product_sha}\n\n{product_body}\n'
    ).encode('utf-8')
    if not 1 <= len(content) <= MAX_EXPORT_BYTES:
        raise ValueError('로컬 상품 결과물은 160KiB 이하여야 합니다.')
    return dict(idea_id=idea_id,business_id=linked['business_id'],
                catalog_id=linked['catalog_id'],review_id=int(review_id),
                research_artifact_id=int(research_id),product_artifact_id=int(product_id),
                model_call_id=linked['model_call_id'],
                review_sha256=receipt,catalog_state=linked['catalog']['state']),content


def _safe_path(store, filename: str) -> Path:
    if (type(filename) is not str or len(filename) != 40
        or not filename.startswith(_FILENAME_PREFIX) or not filename.endswith('.md')
        or any(char not in '0123456789abcdef' for char in filename[5:-3])):
        raise ValueError('로컬 결과물 파일명 원본 손상')
    folder = _folder(store)
    if folder.is_symlink():
        raise ValueError('로컬 결과물 폴더의 심볼릭 링크 금지')
    return folder / filename


def export(store, idea_id: int) -> dict:
    """관리자가 명시적으로 승인할 때만 로컬 파일 1개를 만든다."""
    store.require_permission('company:manage')
    idea_id = _id(idea_id)
    filename = _FILENAME_PREFIX + uuid4().hex + '.md'
    target = _safe_path(store, filename)
    written = False
    committed = False
    try:
        with store._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            initialize(con)
            if stopped(con):
                raise PermissionError('비상정지 중 로컬 결과물 내보내기 금지')
            if con.execute('SELECT 1 FROM aiwack_idea_local_product_exports WHERE idea_id=?',
                           (idea_id,)).fetchone():
                raise ValueError('이 가설의 승인된 로컬 결과물은 이미 내보냈습니다.')
            proof,data = _verified_content(con, idea_id)
            if proof['catalog_state'] != 'review_pending':
                raise PermissionError('내부 검토중인 상품만 로컬 결과물로 내보냅니다.')
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.parent.is_symlink():
                raise ValueError('로컬 결과물 폴더의 심볼릭 링크 금지')
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os,'O_BINARY',0)
            flags |= getattr(os,'O_NOFOLLOW',0)
            fd = os.open(target,flags,0o600)
            written = True
            with os.fdopen(fd,'wb') as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            file_sha = hashlib.sha256(data).hexdigest()
            payload = dict(idea_id=idea_id,business_id=proof['business_id'],
                           catalog_id=proof['catalog_id'],review_id=proof['review_id'],
                           research_artifact_id=proof['research_artifact_id'],
                           product_artifact_id=proof['product_artifact_id'],
                           filename=filename,file_sha256=file_sha,byte_count=len(data))
            export_id = int(con.execute("""INSERT INTO aiwack_idea_local_product_exports
                (idea_id,business_id,catalog_id,review_id,research_artifact_id,
                 product_artifact_id,filename,file_sha256,byte_count,receipt_sha256)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (*payload.values(),_digest(payload))).lastrowid)
        committed = True
        return read(store,export_id)
    except BaseException:
        if written and not committed:
            target.unlink(missing_ok=True)
        raise


def read(store, export_id: int) -> dict:
    """SQLite 원본·실제 직원 결과·파일 바이트를 재대조한다."""
    store.require_permission('company:manage')
    export_id = _id(export_id)
    with store._connect() as con:
        initialize(con)
        row = con.execute("""SELECT idea_id,business_id,catalog_id,review_id,
            research_artifact_id,product_artifact_id,filename,file_sha256,
            byte_count,receipt_sha256 FROM aiwack_idea_local_product_exports
            WHERE id=?""",(export_id,)).fetchone()
        if row is None:
            raise ValueError('로컬 상품 결과물 감사 기록이 없습니다.')
        keys=('idea_id','business_id','catalog_id','review_id','research_artifact_id',
              'product_artifact_id','filename','file_sha256','byte_count')
        record=dict(zip(keys,row[:9]))
        if _digest(record)!=row[9]:
            raise ValueError('로컬 결과물 SQLite 감사 SHA 불일치')
        proof,expected=_verified_content(con,int(record['idea_id']))
        for key in ('business_id','catalog_id','review_id','research_artifact_id',
                    'product_artifact_id'):
            if record[key]!=proof[key]:
                raise ValueError('실제 모델 상품 결과물 출처 연결 손상')
    path = _safe_path(store,record['filename'])
    if path.is_symlink() or not path.is_file():
        raise ValueError('로컬 결과물 파일이 없거나 링크입니다.')
    data=path.read_bytes()
    if (len(data)!=record['byte_count'] or len(data)>MAX_EXPORT_BYTES
        or hashlib.sha256(data).hexdigest()!=record['file_sha256'] or data!=expected):
        raise ValueError('로컬 결과물 파일/SQLite/실제 직원 원본 불일치')
    return dict(id=export_id,idea_id=record['idea_id'],catalog_id=record['catalog_id'],
                review_id=record['review_id'],path=str(path),
                sha256=record['file_sha256'],byte_count=record['byte_count'],
                approved_local_file=True,external_published=False,verified_sales=False)


def inspect(store, limit: int=100) -> list[dict]:
    """원본 누락·변조를 숨기지 않고 개별 FAIL로 반환한다."""
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('로컬 결과물 감사 범위는 1~1000건입니다.')
    with store._connect() as con:
        initialize(con)
        ids=[int(row[0]) for row in con.execute(
            'SELECT id FROM aiwack_idea_local_product_exports ORDER BY id DESC LIMIT ?',
            (limit,)).fetchall()]
    results=[]
    for export_id in ids:
        try:
            record=read(store,export_id)
            results.append(dict(id=export_id,status='PASS',path=record['path'],
                                sha256=record['sha256']))
        except (ValueError,PermissionError,OSError,sqlite3.Error) as exc:
            results.append(dict(id=export_id,status='FAIL',error=str(exc)))
    return results
