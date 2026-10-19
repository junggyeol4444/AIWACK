"""Stage52: fail-closed, local *preflight* authorization ledger.

Approvals NEVER invoke tools, grant employee capabilities, access files, start
subprocesses or authorize money transfers. Future executors must separately
implement an atomic authorization check immediately before any invocation.
"""
from __future__ import annotations

import sqlite3
from desktop.access_policy import CAPABILITIES, TOOLS
from desktop.tool_registry import _id, _text, read


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS tool_use_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_key TEXT NOT NULL UNIQUE CHECK(length(trim(request_key)) BETWEEN 3 AND 100),
        tool_id INTEGER NOT NULL REFERENCES tool_registry(id) ON DELETE RESTRICT,
        employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
        purpose TEXT NOT NULL CHECK(length(trim(purpose)) BETWEEN 1 AND 500),
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','denied')),
        decision_reason TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        decided_at TEXT,
        CHECK((status='pending' AND decision_reason IS NULL AND decided_at IS NULL) OR
              (status IN ('approved','denied') AND length(trim(decision_reason)) BETWEEN 1 AND 500 AND decided_at IS NOT NULL))
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS tool_use_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL REFERENCES tool_use_requests(id) ON DELETE RESTRICT,
        event TEXT NOT NULL CHECK(event IN ('requested','approved','denied')),
        detail TEXT NOT NULL CHECK(length(trim(detail)) BETWEEN 1 AND 500),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    for table in ('tool_use_audit',):
        for event in ('UPDATE','DELETE'):
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{event.lower()}
                BEFORE {event} ON {table} BEGIN SELECT RAISE(ABORT,'tool audit is immutable'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS tool_requests_no_delete
        BEFORE DELETE ON tool_use_requests BEGIN SELECT RAISE(ABORT,'tool request cannot be deleted'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS tool_requests_guard_update
        BEFORE UPDATE ON tool_use_requests BEGIN
        SELECT RAISE(ABORT,'tool request can only be decided once') WHERE
            OLD.status != 'pending' OR NEW.status NOT IN ('approved','denied') OR
            OLD.id != NEW.id OR OLD.request_key IS NOT NEW.request_key OR
            OLD.tool_id != NEW.tool_id OR OLD.employee_id != NEW.employee_id OR
            OLD.purpose IS NOT NEW.purpose OR OLD.created_at IS NOT NEW.created_at OR
            NEW.decided_at IS NULL OR length(trim(NEW.decision_reason)) NOT BETWEEN 1 AND 500;
        END''')


def employee_eligible(con: sqlite3.Connection, employee_id: int, tool: dict) -> tuple[bool, str]:
    row = con.execute('SELECT lifecycle FROM ai_employee_profiles WHERE id=?', (employee_id,)).fetchone()
    if row is None or row[0] != 'draft':
        return False, '직원이 없거나 비활성 상태입니다.'
    if tool['state'] != 'registered':
        return False, '보관된 도구는 사용할 수 없습니다.'
    required = tool['required_capability']
    if not required or required not in CAPABILITIES:
        return False, '필수 직원 권한이 정의되지 않은 도구는 승인할 수 없습니다.'
    granted = con.execute('''SELECT 1 FROM ai_employee_capability_grants
                              WHERE employee_id=? AND capability=?''', (employee_id, required)).fetchone()
    if granted is None:
        return False, '직원에게 필요한 권한이 부여되지 않았습니다.'
    # Registered built-in tool IDs must ALSO satisfy their explicit tool grant.
    if tool['tool_key'] in TOOLS:
        if TOOLS[tool['tool_key']][1] != required:
            return False, '기존 도구의 필요 권한 정의와 충돌합니다.'
        allowed = con.execute('''SELECT 1 FROM ai_employee_tool_grants
                                 WHERE employee_id=? AND tool_key=?''', (employee_id, tool['tool_key'])).fetchone()
        if allowed is None:
            return False, '직원의 기존 도구 허가가 없습니다.'
    return True, '현재 권한과 도구 상태가 일치합니다. (실행 허가는 아님)'


def request(con: sqlite3.Connection, request_key: str, tool_id: int,
            employee_id: int, purpose: str) -> int:
    # The request ID is an idempotency key across restarts. No request grants access.
    import re
    key = _text(request_key, '요청 키', 100)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{2,99}', key):
        raise ValueError('요청 키는 3~100자 영문·숫자·_-만 사용합니다.')
    tool = read(con, tool_id)
    employee_id = _id(employee_id)
    purpose = _text(purpose, '사용 목적', 500)
    if tool['state'] != 'registered':
        raise ValueError('보관된 도구에는 요청할 수 없습니다.')
    if con.execute('SELECT 1 FROM ai_employee_profiles WHERE id=?', (employee_id,)).fetchone() is None:
        raise ValueError('직원 기록이 없습니다.')
    try:
        cursor = con.execute('''INSERT INTO tool_use_requests(request_key,tool_id,employee_id,purpose)
            VALUES(?,?,?,?)''', (key,tool_id,employee_id,purpose))
    except sqlite3.IntegrityError as exc:
        raise ValueError('중복되거나 유효하지 않은 요청 키입니다.') from exc
    rid = int(cursor.lastrowid)
    con.execute('INSERT INTO tool_use_audit(request_id,event,detail) VALUES(?,?,?)',
                (rid,'requested','관리자 요청 등록: 승인 및 실행 없음'))
    return rid


def get_request(con: sqlite3.Connection, request_id: int) -> dict:
    con.row_factory = sqlite3.Row
    row = con.execute('''SELECT r.*, t.tool_key, t.name AS tool_name,
            t.category, t.required_capability, t.state AS tool_state,
            e.display_name AS employee_name, e.lifecycle AS employee_state
            FROM tool_use_requests r
            JOIN tool_registry t ON r.tool_id=t.id
            JOIN ai_employee_profiles e ON r.employee_id=e.id
            WHERE r.id=?''', (_id(request_id),)).fetchone()
    if row is None:
        raise ValueError('도구 사용 요청이 존재하지 않습니다.')
    return dict(row)


def list_requests(con: sqlite3.Connection, limit: int = 200) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('목록 제한은 1~1000 정수여야 합니다.')
    con.row_factory = sqlite3.Row
    return [dict(row) for row in con.execute('''SELECT r.id, r.request_key, r.tool_id,
        t.name AS tool_name, r.employee_id, e.display_name AS employee_name,
        r.purpose, r.status, r.created_at, r.decided_at FROM tool_use_requests r
        JOIN tool_registry t ON r.tool_id=t.id
        JOIN ai_employee_profiles e ON r.employee_id=e.id
        ORDER BY r.id DESC LIMIT ?''', (limit,))]


def decide(con: sqlite3.Connection, request_id: int, decision: str, reason: str) -> bool:
    if decision not in ('approved','denied'):
        raise ValueError('승인 또는 반려만 선택할 수 있습니다.')
    reason = _text(reason, '결정 사유', 500)
    entry = get_request(con, request_id)
    if entry['status'] != 'pending':
        raise ValueError('이미 결정된 요청입니다.')
    if decision == 'approved':
        tool = read(con, entry['tool_id'])
        valid, message = employee_eligible(con, entry['employee_id'], tool)
        if not valid:
            raise PermissionError(message)
    result = con.execute('''UPDATE tool_use_requests SET status=?,decision_reason=?,decided_at=CURRENT_TIMESTAMP
        WHERE id=? AND status='pending' ''', (decision,reason,request_id))
    if result.rowcount != 1:
        raise ValueError('요청이 다른 처리에서 이미 결정되었습니다.')
    con.execute('INSERT INTO tool_use_audit(request_id,event,detail) VALUES(?,?,?)',
                (request_id,decision,reason))
    return True


def preflight(con: sqlite3.Connection, request_id: int) -> dict:
    entry = get_request(con, request_id)
    if entry['status'] != 'approved':
        return {'allowed': False, 'reason': '관리자 승인이 없습니다.', 'execution_performed': False}
    tool = read(con, entry['tool_id'])
    valid, reason = employee_eligible(con, entry['employee_id'], tool)
    return {'allowed': valid, 'reason': reason, 'execution_performed': False}


def audit(con: sqlite3.Connection, request_id: int) -> list[dict]:
    get_request(con, request_id)
    con.row_factory = sqlite3.Row
    return [dict(row) for row in con.execute('SELECT * FROM tool_use_audit WHERE request_id=? ORDER BY id', (request_id,))]
