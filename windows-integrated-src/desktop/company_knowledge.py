"""Stage48: append-only, owner-managed company knowledge documents (offline).

Company-wide is an organizational category; no AI/employee read permission is
implicitly granted. Fine-grained access/source validation is for later stages.
"""
from __future__ import annotations

import sqlite3

KINDS = frozenset({'policy', 'procedure', 'research', 'business_plan', 'development',
                   'product', 'case_study', 'meeting', 'other'})


def initialize(con: sqlite3.Connection) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS company_knowledge_documents (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      kind TEXT NOT NULL CHECK(kind IN ('policy','procedure','research','business_plan',
          'development','product','case_study','meeting','other')),
      title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 160),
      content TEXT NOT NULL CHECK(length(trim(content)) BETWEEN 1 AND 10000),
      source TEXT NOT NULL CHECK(length(trim(source)) BETWEEN 1 AND 500),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      archived_at TEXT
    )""")
    con.execute('CREATE INDEX IF NOT EXISTS idx_company_knowledge_created ON company_knowledge_documents(id DESC)')
    con.execute("""CREATE TRIGGER IF NOT EXISTS company_knowledge_immutable
      BEFORE UPDATE ON company_knowledge_documents BEGIN
      SELECT RAISE(ABORT,'knowledge document contents are immutable; archive instead')
        WHERE OLD.kind IS NOT NEW.kind OR OLD.title IS NOT NEW.title
           OR OLD.content IS NOT NEW.content OR OLD.source IS NOT NEW.source
           OR OLD.created_at IS NOT NEW.created_at
           OR OLD.archived_at IS NOT NULL OR NEW.archived_at IS NULL;
    END""")
    con.execute("""CREATE TRIGGER IF NOT EXISTS company_knowledge_no_delete
      BEFORE DELETE ON company_knowledge_documents BEGIN
        SELECT RAISE(ABORT,'knowledge documents cannot be deleted');
    END""")


def _required(value, label, maximum):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise ValueError(f'{label}은 1~{maximum}자여야 합니다.')
    return value.strip()


def _id(value):
    if type(value) is not int or value < 1:
        raise ValueError('올바른 문서 ID가 필요합니다.')
    return value


def create(con, kind, title, content, source):
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError('지원하지 않는 문서 분류입니다.')
    title = _required(title, '제목', 160)
    content = _required(content, '본문', 10000)
    source = _required(source, '출처', 500)
    return con.execute('''INSERT INTO company_knowledge_documents(kind,title,content,source)
        VALUES(?,?,?,?)''', (kind, title, content, source)).lastrowid


def read(con, document_id):
    _id(document_id)
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM company_knowledge_documents WHERE id=?', (document_id,)).fetchone()
    if row is None:
        raise ValueError('지식 문서를 찾을 수 없습니다.')
    return dict(row)


def list_documents(con, *, include_archived=False, limit=200):
    if type(include_archived) is not bool:
        raise ValueError('조회 옵션이 올바르지 않습니다.')
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('조회 건수는 1~500 사이여야 합니다.')
    sql = 'SELECT id, kind, title, source, created_at, archived_at FROM company_knowledge_documents'
    if not include_archived:
        sql += ' WHERE archived_at IS NULL'
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(sql+' ORDER BY id DESC LIMIT ?', (limit,))]


def archive(con, document_id):
    _id(document_id)
    changed = con.execute('''UPDATE company_knowledge_documents
        SET archived_at=CURRENT_TIMESTAMP WHERE id=? AND archived_at IS NULL''',
                          (document_id,))
    if changed.rowcount != 1:
        raise ValueError('문서가 없거나 이미 보관되었습니다.')
    return True
