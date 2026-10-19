"""Stage49: offline owner-administered document search, provenance and *preview* ACL.

There is no authenticated employee principal yet. `preview_*` simulates an employee
read as an owner-only diagnostic; it is NOT an agent login or runtime enforcement.
Existing Stage48 documents default to owner-only access, never public.
"""
from __future__ import annotations

import sqlite3

MODES = frozenset({'owner_only', 'restricted', 'company'})
SOURCE_TYPES = frozenset({'manual', 'local_file', 'internal_record', 'website_reference'})


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS knowledge_access_policy (
        document_id INTEGER PRIMARY KEY REFERENCES company_knowledge_documents(id) ON DELETE RESTRICT,
        mode TEXT NOT NULL CHECK(mode IN ('owner_only','restricted','company')),
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS knowledge_read_grants (
        document_id INTEGER NOT NULL REFERENCES company_knowledge_documents(id) ON DELETE RESTRICT,
        employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
        granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(document_id,employee_id)
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS knowledge_provenance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL REFERENCES company_knowledge_documents(id) ON DELETE RESTRICT,
        source_type TEXT NOT NULL CHECK(source_type IN
            ('manual','local_file','internal_record','website_reference')),
        reference TEXT NOT NULL CHECK(length(trim(reference)) BETWEEN 1 AND 500),
        recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        validation_status TEXT NOT NULL DEFAULT 'unverified' CHECK(validation_status='unverified')
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_provenance_doc ON knowledge_provenance(document_id,id)')
    con.execute('''CREATE TRIGGER IF NOT EXISTS knowledge_provenance_no_update
        BEFORE UPDATE ON knowledge_provenance BEGIN
        SELECT RAISE(ABORT, 'source records are append-only'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS knowledge_provenance_no_delete
        BEFORE DELETE ON knowledge_provenance BEGIN
        SELECT RAISE(ABORT, 'source records cannot be deleted'); END''')
    con.execute('''CREATE TABLE IF NOT EXISTS knowledge_access_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL REFERENCES company_knowledge_documents(id) ON DELETE RESTRICT,
        action TEXT NOT NULL CHECK(action IN ('mode','grant','revoke')),
        employee_id INTEGER REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
        detail TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS knowledge_access_audit_no_update
        BEFORE UPDATE ON knowledge_access_audit BEGIN
        SELECT RAISE(ABORT, 'access audit is append-only'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS knowledge_access_audit_no_delete
        BEFORE DELETE ON knowledge_access_audit BEGIN
        SELECT RAISE(ABORT, 'access audit cannot be deleted'); END''')


def _positive_int(value, label):
    if type(value) is not int or value < 1:
        raise ValueError(f'올바른 {label}가 필요합니다.')
    return value


def _document(con, document_id, *, active=False):
    _positive_int(document_id, '문서 ID')
    result = con.execute('SELECT archived_at FROM company_knowledge_documents WHERE id=?', (document_id,)).fetchone()
    if result is None or (active and result[0] is not None):
        raise ValueError('문서를 찾을 수 없거나 보관되었습니다.')
    return result


def _employee(con, employee_id):
    _positive_int(employee_id, '직원 ID')
    row = con.execute('SELECT lifecycle FROM ai_employee_profiles WHERE id=?', (employee_id,)).fetchone()
    if row is None or row[0] != 'draft':
        raise ValueError('활성 직원만 조회 권한을 받을 수 있습니다.')


def mode(con, document_id):
    _document(con, document_id)
    row = con.execute('SELECT mode FROM knowledge_access_policy WHERE document_id=?', (document_id,)).fetchone()
    return row[0] if row else 'owner_only'


def set_mode(con, document_id, new_mode):
    _document(con, document_id, active=True)
    if type(new_mode) is not str or new_mode not in MODES:
        raise ValueError('지원하지 않는 접근 범위입니다.')
    old = mode(con, document_id)
    if old == new_mode:
        return False
    con.execute('''INSERT INTO knowledge_access_policy(document_id,mode) VALUES(?,?)
        ON CONFLICT(document_id) DO UPDATE SET mode=excluded.mode,updated_at=CURRENT_TIMESTAMP''',
        (document_id, new_mode))
    if new_mode != 'restricted':
        con.execute('DELETE FROM knowledge_read_grants WHERE document_id=?', (document_id,))
    con.execute('INSERT INTO knowledge_access_audit(document_id,action,detail) VALUES(?,?,?)',
                (document_id, 'mode', f'{old} -> {new_mode}'))
    return True


def grant(con, document_id, employee_id):
    _document(con, document_id, active=True)
    _employee(con, employee_id)
    if mode(con, document_id) != 'restricted':
        raise ValueError('선택 직원 공개 상태에서만 권한을 부여할 수 있습니다.')
    result = con.execute('INSERT OR IGNORE INTO knowledge_read_grants(document_id,employee_id) VALUES(?,?)',
                         (document_id, employee_id))
    if result.rowcount:
        con.execute('INSERT INTO knowledge_access_audit(document_id,action,employee_id,detail) VALUES(?,?,?,?)',
                    (document_id, 'grant', employee_id, 'read'))
    return result.rowcount == 1


def revoke(con, document_id, employee_id):
    _document(con, document_id, active=True)
    _positive_int(employee_id, '직원 ID')
    result = con.execute('DELETE FROM knowledge_read_grants WHERE document_id=? AND employee_id=?',
                         (document_id, employee_id))
    if result.rowcount:
        con.execute('INSERT INTO knowledge_access_audit(document_id,action,employee_id,detail) VALUES(?,?,?,?)',
                    (document_id, 'revoke', employee_id, 'read'))
    return result.rowcount == 1


def access_info(con, document_id):
    _document(con, document_id)
    return dict(mode=mode(con, document_id), employees=[r[0] for r in con.execute(
        'SELECT employee_id FROM knowledge_read_grants WHERE document_id=? ORDER BY employee_id',
        (document_id,))], audit=[dict(zip(('action','employee_id','detail','created_at'),r)) for r in con.execute(
        'SELECT action,employee_id,detail,created_at FROM knowledge_access_audit WHERE document_id=? ORDER BY id',
        (document_id,))])


def add_source(con, document_id, source_type, reference):
    _document(con, document_id, active=True)
    if type(source_type) is not str or source_type not in SOURCE_TYPES:
        raise ValueError('지원하지 않는 출처 유형입니다.')
    if type(reference) is not str or not 1 <= len(reference.strip()) <= 500:
        raise ValueError('출처 참조는 1~500자여야 합니다.')
    return con.execute('INSERT INTO knowledge_provenance(document_id,source_type,reference) VALUES(?,?,?)',
                       (document_id, source_type, reference.strip())).lastrowid


def list_sources(con, document_id):
    _document(con, document_id)
    return [dict(zip(('id','document_id','source_type','reference','recorded_at','validation_status'),r))
            for r in con.execute('''SELECT id,document_id,source_type,reference,recorded_at,validation_status
              FROM knowledge_provenance WHERE document_id=? ORDER BY id''', (document_id,))]


def search(con, query='', *, employee_id=None, include_archived=False, limit=200):
    if type(query) is not str or len(query) > 120:
        raise ValueError('검색어는 120자 이하여야 합니다.')
    if type(include_archived) is not bool or type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('검색 옵션이 올바르지 않습니다.')
    if employee_id is not None:
        _employee(con, employee_id)
        # Archived documents are never shown to employees, even with include_archived=True.
        if include_archived:
            raise ValueError('직원 권한 미리보기에서는 보관 문서를 조회할 수 없습니다.')
    sql = '''SELECT d.id,d.kind,d.title,d.source,d.created_at,d.archived_at
      FROM company_knowledge_documents AS d WHERE 1=1'''
    args = []
    if not include_archived:
        sql += ' AND d.archived_at IS NULL'
    if employee_id is not None:
        sql += ''' AND (COALESCE((SELECT mode FROM knowledge_access_policy p WHERE p.document_id=d.id), 'owner_only')='company'
            OR (COALESCE((SELECT mode FROM knowledge_access_policy p WHERE p.document_id=d.id), 'owner_only')='restricted'
            AND EXISTS (SELECT 1 FROM knowledge_read_grants g WHERE g.document_id=d.id AND g.employee_id=?)))'''
        args.append(employee_id)
    if query.strip():
        # instr gives literal substring search; '%' and '_' are not LIKE wildcards.
        sql += ''' AND (instr(d.title,?)>0 OR instr(d.content,?)>0 OR instr(d.source,?)>0
           OR EXISTS (SELECT 1 FROM knowledge_provenance s WHERE s.document_id=d.id AND instr(s.reference,?)>0))'''
        args.extend([query.strip()] * 4)
    sql += ' ORDER BY d.id DESC LIMIT ?'
    args.append(limit)
    return [dict(zip(('id','kind','title','source','created_at','archived_at'),r))
            for r in con.execute(sql,args)]


def preview_read(con, document_id, employee_id):
    _document(con, document_id, active=True)
    _employee(con, employee_id)
    if mode(con, document_id) == 'owner_only' or (
        mode(con, document_id) == 'restricted' and not con.execute(
            'SELECT 1 FROM knowledge_read_grants WHERE document_id=? AND employee_id=?',
            (document_id,employee_id)).fetchone()
    ):
        raise PermissionError('이 직원에게 문서 읽기 권한이 없습니다.')
    row = con.execute('SELECT * FROM company_knowledge_documents WHERE id=?', (document_id,)).fetchone()
    columns = [d[1] for d in con.execute('PRAGMA table_info(company_knowledge_documents)')]
    return dict(zip(columns,row))
