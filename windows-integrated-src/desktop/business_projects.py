"""Stage66: owner-operated offline business/project register and existing-task links.

No autonomous project execution, external accounts, spending or real revenue.
The SQLite audit checksums are local integrity aids, not cryptographic signatures.
Stage43 project *chat rooms* are separate and intentionally not reinterpreted.
"""
from __future__ import annotations

import json
import sqlite3

from desktop.business_portfolio import _hash, _id, _label

STATES = ('planned', 'active', 'paused', 'completed', 'cancelled')
TRANSITIONS = {
    'planned': {'active', 'cancelled'},
    'active': {'paused', 'completed', 'cancelled'},
    'paused': {'active', 'completed', 'cancelled'},
    'completed': set(), 'cancelled': set(),
}


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS managed_business_projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id INTEGER NOT NULL REFERENCES managed_businesses(id) ON DELETE RESTRICT,
        title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 120),
        objective TEXT NOT NULL CHECK(length(objective) BETWEEN 1 AND 500),
        planned_budget_krw INTEGER NOT NULL CHECK(planned_budget_krw BETWEEN 0 AND 1000000000000),
        responsible_employee_id INTEGER REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
        state TEXT NOT NULL DEFAULT 'planned'
            CHECK(state IN ('planned','active','paused','completed','cancelled')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS managed_project_task_links (
        task_id INTEGER PRIMARY KEY REFERENCES company_tasks(id) ON DELETE RESTRICT,
        project_id INTEGER NOT NULL REFERENCES managed_business_projects(id) ON DELETE RESTRICT,
        linked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS managed_project_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES managed_business_projects(id) ON DELETE RESTRICT,
        action TEXT NOT NULL CHECK(action IN ('created','state_changed','task_linked','task_unlinked')),
        detail_json TEXT NOT NULL,
        previous_digest TEXT NOT NULL,
        digest TEXT NOT NULL CHECK(length(digest)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_managed_projects_business ON managed_business_projects(business_id,id)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_managed_project_events ON managed_project_events(project_id,id)')
    for table in ('managed_project_events',):
        for op in ('UPDATE','DELETE'):
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()}
                BEFORE {op} ON {table} BEGIN
                SELECT RAISE(ABORT, 'project audit is append-only'); END''')
    for op in ('DELETE',):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS managed_business_projects_no_{op.lower()}
            BEFORE {op} ON managed_business_projects BEGIN
            SELECT RAISE(ABORT, 'project history is preserved'); END''')
    # Identity and budget cannot be rewritten after audit creation.
    con.execute('''CREATE TRIGGER IF NOT EXISTS managed_business_projects_identity_guard
        BEFORE UPDATE OF business_id,title,objective,planned_budget_krw,responsible_employee_id
        ON managed_business_projects BEGIN
        SELECT RAISE(ABORT,'project identity and budget are immutable'); END''')


def _project_row(con: sqlite3.Connection, project_id: int) -> dict:
    _id(project_id, '프로젝트')
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM managed_business_projects WHERE id=?', (project_id,)).fetchone()
    if row is None:
        raise ValueError('프로젝트가 존재하지 않습니다.')
    return dict(row)


def _event(con: sqlite3.Connection, project_id: int, action: str, payload: dict) -> None:
    previous = con.execute('SELECT digest FROM managed_project_events WHERE project_id=? ORDER BY id DESC LIMIT 1',
                           (project_id,)).fetchone()
    prev = previous[0] if previous else ''
    detail = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    if len(detail) > 1800:
        raise ValueError('감사 기록이 너무 깁니다.')
    digest = _hash({'project_id': project_id, 'action': action,
                    'payload': payload, 'previous_digest': prev})
    con.execute('''INSERT INTO managed_project_events(project_id,action,detail_json,previous_digest,digest)
                   VALUES (?,?,?,?,?)''', (project_id, action, detail, prev, digest))


def create(con: sqlite3.Connection, business_id: int, title: str, objective: str,
           planned_budget_krw: int = 0, responsible_employee_id: int | None = None) -> int:
    _id(business_id, '사업')
    title = _label(title, '프로젝트명', 120)
    objective = _label(objective, '프로젝트 목표', 500)
    if type(planned_budget_krw) is not int or not 0 <= planned_budget_krw <= 1_000_000_000_000:
        raise ValueError('계획 예산은 0~1조 원 정수여야 합니다.')
    business = con.execute('SELECT state FROM managed_businesses WHERE id=?', (business_id,)).fetchone()
    if not business or business[0] == 'closed':
        raise ValueError('존재하지 않거나 종료된 사업입니다.')
    if responsible_employee_id is not None:
        _id(responsible_employee_id, '담당 직원')
        if not con.execute('''SELECT 1 FROM business_participants bp
            JOIN ai_employee_profiles e ON e.id=bp.employee_id
            WHERE bp.business_id=? AND bp.employee_id=? AND e.lifecycle='draft' ''',
            (business_id, responsible_employee_id)).fetchone():
            raise ValueError('해당 사업에 참여하는 활성 AI 직원만 담당할 수 있습니다.')
    cursor = con.execute('''INSERT INTO managed_business_projects
        (business_id,title,objective,planned_budget_krw,responsible_employee_id)
        VALUES (?,?,?,?,?)''', (business_id,title,objective,planned_budget_krw,responsible_employee_id))
    project_id = int(cursor.lastrowid)
    _event(con, project_id, 'created', {'business_id': business_id, 'title': title,
           'objective': objective, 'planned_budget_krw': planned_budget_krw,
           'responsible_employee_id': responsible_employee_id, 'state': 'planned'})
    return project_id


def get(con: sqlite3.Connection, project_id: int) -> dict:
    project = _project_row(con, project_id)
    con.row_factory = sqlite3.Row
    events = con.execute('SELECT * FROM managed_project_events WHERE project_id=? ORDER BY id',
                         (project_id,)).fetchall()
    if not events or events[0]['action'] != 'created':
        raise ValueError('프로젝트 감사 생성 기록 누락')
    prev = ''
    state = 'planned'
    linked_tasks: set[int] = set()
    for index, event in enumerate(events):
        try:
            payload = json.loads(event['detail_json'])
        except (TypeError, ValueError) as exc:
            raise ValueError('프로젝트 감사 JSON 손상') from exc
        if event['previous_digest'] != prev or event['digest'] != _hash({
                'project_id': project_id, 'action': event['action'],
                'payload': payload, 'previous_digest': prev}):
            raise ValueError('프로젝트 감사 무결성 오류')
        action = event['action']
        if index == 0:
            expected = {key: project[key] for key in
                        ('business_id','title','objective','planned_budget_krw','responsible_employee_id')}
            expected['state'] = 'planned'
            if action != 'created' or payload != expected:
                raise ValueError('프로젝트 생성 감사 불일치')
        elif action == 'state_changed':
            if payload != {'from': state, 'to': payload.get('to')} or payload.get('to') not in TRANSITIONS[state]:
                raise ValueError('프로젝트 상태 감사 불일치')
            state = payload['to']
        elif action == 'task_linked':
            task_id = payload.get('task_id')
            if type(task_id) is not int or task_id < 1 or task_id in linked_tasks:
                raise ValueError('프로젝트 업무 연결 감사 불일치')
            linked_tasks.add(task_id)
        elif action == 'task_unlinked':
            task_id = payload.get('task_id')
            if type(task_id) is not int or task_id not in linked_tasks:
                raise ValueError('프로젝트 업무 해제 감사 불일치')
            linked_tasks.remove(task_id)
        else:
            raise ValueError('프로젝트 감사 동작 오류')
        prev = event['digest']
    actual = {row[0] for row in con.execute(
        'SELECT task_id FROM managed_project_task_links WHERE project_id=?', (project_id,))}
    if state != project['state'] or linked_tasks != actual:
        raise ValueError('프로젝트 상태/업무 연결 감사 불일치')
    project['task_ids'] = sorted(linked_tasks)
    project['task_count'] = len(linked_tasks)
    project['external_actions_executed'] = False
    project['autonomous_execution_performed'] = False
    return project


def list_projects(con: sqlite3.Connection, business_id: int | None = None, limit: int = 100) -> list[dict]:
    if business_id is not None:
        _id(business_id, '사업')
        if not con.execute('SELECT 1 FROM managed_businesses WHERE id=?', (business_id,)).fetchone():
            raise ValueError('사업이 존재하지 않습니다.')
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('조회 개수는 1~200입니다.')
    where = '' if business_id is None else ' WHERE business_id=?'
    args = (limit,) if business_id is None else (business_id,limit)
    ids = [row[0] for row in con.execute(
        'SELECT id FROM managed_business_projects' + where + ' ORDER BY id DESC LIMIT ?', args)]
    return [get(con, project_id) for project_id in ids]


def change_state(con: sqlite3.Connection, project_id: int, new_state: str) -> dict:
    item = get(con, project_id)
    if type(new_state) is not str or new_state not in TRANSITIONS[item['state']]:
        raise ValueError('프로젝트 상태 전환이 허용되지 않습니다.')
    business = con.execute('SELECT state FROM managed_businesses WHERE id=?',
                           (item['business_id'],)).fetchone()
    if new_state == 'active' and business[0] == 'closed':
        raise ValueError('종료된 사업에서는 프로젝트를 활성화할 수 없습니다.')
    con.execute('UPDATE managed_business_projects SET state=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                (new_state, project_id))
    _event(con, project_id, 'state_changed', {'from': item['state'], 'to': new_state})
    return get(con, project_id)


def set_task_link(con: sqlite3.Connection, project_id: int, task_id: int, add: bool) -> dict:
    item = get(con, project_id)
    _id(task_id, '업무')
    if type(add) is not bool:
        raise ValueError('업무 연결 옵션이 유효하지 않습니다.')
    if item['state'] in ('completed','cancelled'):
        raise ValueError('종료된 프로젝트의 업무 연결을 변경할 수 없습니다.')
    if add:
        if not con.execute('SELECT 1 FROM company_tasks WHERE id=?', (task_id,)).fetchone():
            raise ValueError('기존 업무 ID가 존재하지 않습니다.')
        existing = con.execute('SELECT project_id FROM managed_project_task_links WHERE task_id=?',
                               (task_id,)).fetchone()
        if existing:
            raise ValueError('해당 업무는 이미 프로젝트에 연결되어 있습니다.')
        con.execute('INSERT INTO managed_project_task_links(task_id,project_id) VALUES (?,?)',
                    (task_id, project_id))
        _event(con, project_id, 'task_linked', {'task_id': task_id})
    else:
        result = con.execute('DELETE FROM managed_project_task_links WHERE task_id=? AND project_id=?',
                             (task_id, project_id))
        if result.rowcount != 1:
            raise ValueError('연결되지 않은 업무입니다.')
        _event(con, project_id, 'task_unlinked', {'task_id': task_id})
    return get(con, project_id)


def events(con: sqlite3.Connection, project_id: int) -> list[dict]:
    get(con, project_id)  # Verify all events and state before returning.
    con.row_factory = sqlite3.Row
    return [dict(row) for row in con.execute(
        'SELECT id,action,detail_json,previous_digest,digest,created_at FROM managed_project_events WHERE project_id=? ORDER BY id',
        (project_id,))]
