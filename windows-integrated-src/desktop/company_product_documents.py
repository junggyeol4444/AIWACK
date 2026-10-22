"""승인된 실제 AI 직원 결과물을 기존 상품 카탈로그의 로컬 Markdown 문서로 연결.

새로운 모의 AI 결과를 만들지 않는다. 반드시 기존 30업무 승인 체인과
직원 실행/총괄 검토/관리자 결과물 승인의 SQLite 증빙을 다시 검사한다.
파일 생성은 관리자 직접 명령으로만 수행되며 외부 게시·계약·결제는 없다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
from uuid import uuid4

from desktop.company_wide_campaign import initialize as init_campaign
from desktop.company_wide_campaign import _verified_step_evidence
from desktop.product_catalog import get as get_catalog
from desktop.stage87_90_management import stopped

MAX_DOCUMENT_BYTES = 32 * 1024


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_approved_product_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL REFERENCES aiwack_wide_campaigns(id),
        ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 30),
        catalog_item_id INTEGER NOT NULL REFERENCES local_catalog_items(id),
        artifact_id INTEGER NOT NULL REFERENCES company_task_artifacts(id),
        artifact_sha256 TEXT NOT NULL CHECK(length(artifact_sha256)=64),
        chief_report_sha256 TEXT NOT NULL CHECK(length(chief_report_sha256)=64),
        filename TEXT NOT NULL UNIQUE,
        file_sha256 TEXT NOT NULL CHECK(length(file_sha256)=64),
        byte_count INTEGER NOT NULL CHECK(byte_count BETWEEN 1 AND 32768),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(campaign_id,ordinal,catalog_item_id))''')
    for operation in ('UPDATE', 'DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS aiwack_approved_product_documents_no_{operation.lower()}
            BEFORE {operation} ON aiwack_approved_product_documents BEGIN
            SELECT RAISE(ABORT,'승인된 로컬 상품 문서 이력 수정·삭제 불가'); END''')


def _folder(store) -> Path:
    return Path(store.path).resolve().parent / 'aiwack_approved_documents'


def _content(con, campaign_id: int, ordinal: int, catalog_id: int):
    init_campaign(con)
    from desktop.product_catalog import initialize as init_catalog
    init_catalog(con)
    initialize(con)
    plan = con.execute('''SELECT chief_employee_id,state FROM aiwack_wide_campaigns
                          WHERE id=?''', (campaign_id,)).fetchone()
    if not plan or plan[1] != 'approved':
        raise ValueError('승인된 30업무 계획만 상품 문서로 연결할 수 있습니다.')
    proof = _verified_step_evidence(con, campaign_id, ordinal, expected_chief=int(plan[0]))
    if proof is None:
        raise ValueError('실제 직원 결과·총괄 보고·관리자 승인 무결성이 확인되지 않았습니다.')
    catalog = get_catalog(con, catalog_id)
    if catalog['state'] == 'archived':
        raise ValueError('보관된 상품에는 결과물을 연결할 수 없습니다.')
    row = con.execute('''SELECT a.title,a.body,a.sha256,rep.body,rep.sha256
        FROM company_task_artifacts a
        JOIN company_chief_task_reports rep ON rep.artifact_id=a.id
        WHERE a.id=? AND a.review_status='approved' AND rep.owner_decision='accepted' ''',
        (proof['artifact_id'],)).fetchone()
    if not row or row[2] != proof['artifact_sha256'] or row[4] != proof['chief_report_sha256']:
        raise ValueError('승인 원본과 총괄 보고 감사 기록이 일치하지 않습니다.')
    title, body, artifact_sha, report, report_sha = row
    # Both text bodies are actual persisted employee/chief results, not synthesized.
    data = (f'# {title}\n\n{body}\n\n---\n'
            f'검수 기록: 관리자 승인된 결과물 #{proof["artifact_id"]}\n'
            f'총괄 보고(관리자 수락):\n{report}\n').encode('utf-8')
    if not 1 <= len(data) <= MAX_DOCUMENT_BYTES:
        raise ValueError('승인 문서의 파일 크기는 32KiB 이하여야 합니다.')
    return proof, data, catalog


def export(store, campaign_id: int, ordinal: int, catalog_item_id: int) -> dict:
    """Only explicit authenticated owner action creates an immutable local file."""
    store.require_permission('company:manage')
    for label, value in (('전체 협업',campaign_id),('단계',ordinal),('상품',catalog_item_id)):
        if type(value) is not int or value <= 0:
            raise ValueError(label+' 번호는 양의 정수여야 합니다.')
    if ordinal > 30:raise ValueError('30개 업무의 단계만 허용합니다.')
    folder = _folder(store)
    if folder.is_symlink():raise ValueError('상품 결과 폴더의 심볼릭 링크 금지')
    filename = 'approved_' + uuid4().hex + '.md'
    target = folder / filename
    written = False
    committed = False
    try:
        with store._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            if stopped(con):raise PermissionError('비상정지 중에는 결과물 파일을 생성할 수 없습니다.')
            proof, data, catalog = _content(con,campaign_id,ordinal,catalog_item_id)
            if con.execute('''SELECT 1 FROM aiwack_approved_product_documents
                  WHERE campaign_id=? AND ordinal=? AND catalog_item_id=?''',
                  (campaign_id,ordinal,catalog_item_id)).fetchone():
                raise ValueError('동일 승인 업무의 상품 문서가 이미 존재합니다.')
            folder.mkdir(parents=True, exist_ok=True)
            if folder.is_symlink():raise ValueError('상품 결과 폴더의 심볼릭 링크 금지')
            with target.open('xb') as output:
                output.write(data)
            written = True
            row_id = int(con.execute('''INSERT INTO aiwack_approved_product_documents
                (campaign_id,ordinal,catalog_item_id,artifact_id,artifact_sha256,
                 chief_report_sha256,filename,file_sha256,byte_count)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (campaign_id,ordinal,catalog_item_id,proof['artifact_id'],
                 proof['artifact_sha256'],proof['chief_report_sha256'],filename,
                 hashlib.sha256(data).hexdigest(),len(data))).lastrowid)
        committed = True
        # A post-commit read failure must not delete the file referenced by a
        # durable SQLite row; otherwise the next login cannot recover it.
        return read(store,row_id)
    except BaseException:
        if written and not committed:
            target.unlink(missing_ok=True)
        raise


def read(store, document_id: int) -> dict:
    store.require_permission('company:manage')
    if type(document_id) is not int or document_id <= 0:
        raise ValueError('문서 번호 오류')
    with store._connect() as con:
        initialize(con)
        row=con.execute('''SELECT campaign_id,ordinal,catalog_item_id,artifact_id,
            artifact_sha256,chief_report_sha256,filename,file_sha256,byte_count
            FROM aiwack_approved_product_documents WHERE id=?''',(document_id,)).fetchone()
        if row is None:raise ValueError('승인 로컬 상품 문서 없음')
        campaign,ordinal,catalog_id,artifact,artifact_sha,report_sha,filename,digest,length=row
        proof,data,_ = _content(con,int(campaign),int(ordinal),int(catalog_id))
        if (proof['artifact_id']!=artifact or proof['artifact_sha256']!=artifact_sha
              or proof['chief_report_sha256']!=report_sha):
            raise ValueError('상품 문서와 원본 승인 결과가 일치하지 않습니다.')
    if (not isinstance(filename,str) or not filename.startswith('approved_') or
        len(filename)!=44 or not filename.endswith('.md') or
        any(ch not in '0123456789abcdef' for ch in filename[9:-3])):
        raise ValueError('상품 문서 경로 감사 오류')
    folder=_folder(store)
    path=folder/filename
    if folder.is_symlink() or path.is_symlink() or not path.is_file():
        raise ValueError('승인 상품 문서 파일이 없거나 링크입니다.')
    raw=path.read_bytes()
    if (len(raw)!=length or len(raw)>MAX_DOCUMENT_BYTES or
        hashlib.sha256(raw).hexdigest()!=digest or raw!=data):
        raise ValueError('상품 문서 원본·해시·내용의 무결성이 훼손됐습니다.')
    return {'id':document_id,'catalog_item_id':catalog_id,'campaign_id':campaign,
            'ordinal':ordinal,'artifact_id':artifact,'path':str(path),
            'sha256':digest,'byte_count':length,'approved_local_file':True,
            'external_published':False,'actual_sale_confirmed':False,
            'real_gguf_binary_attested':False}