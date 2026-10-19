"""Stage65: offline *review briefs* for the owner's business decisions.

Not chief-AI inference, autonomous business selection, financial advice, approval
for real execution, or a bridge to an external service. All monetary figures are
unverified Stage64 owner assumptions; comparisons are descriptive only.
"""
from __future__ import annotations

import json
import sqlite3

from desktop.business_portfolio import _hash, _id, _label
from desktop.financial_feasibility import report as financial_report

MAX_BRIEFS = 5000
MAX_ITEMS = 10


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS chief_business_briefs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      snapshot_json TEXT NOT NULL CHECK(length(snapshot_json) BETWEEN 2 AND 12000),
      snapshot_digest TEXT NOT NULL CHECK(length(snapshot_digest)=64),
      owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 1 AND 300),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS chief_business_brief_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      brief_id INTEGER NOT NULL REFERENCES chief_business_briefs(id) ON DELETE RESTRICT,
      action TEXT NOT NULL CHECK(action IN ('created','acknowledged','rejected')),
      detail_json TEXT NOT NULL CHECK(length(detail_json) BETWEEN 2 AND 1000),
      detail_digest TEXT NOT NULL CHECK(length(detail_digest)=64),
      previous_digest TEXT NOT NULL CHECK(length(previous_digest) IN (0,64)),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS chief_business_events_idx ON chief_business_brief_events(brief_id,id)')
    for table in ('chief_business_briefs', 'chief_business_brief_events'):
        for op in ('UPDATE', 'DELETE'):
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()}
              BEFORE {op} ON {table} BEGIN
              SELECT RAISE(ABORT, 'chief decision audit is append-only'); END''')


def _event(con: sqlite3.Connection, brief_id: int, action: str, payload: dict) -> None:
    previous = con.execute('''SELECT detail_digest FROM chief_business_brief_events
                              WHERE brief_id=? ORDER BY id DESC LIMIT 1''', (brief_id,)).fetchone()
    previous_digest = previous[0] if previous else ''
    detail = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    digest = _hash({'brief_id': brief_id, 'action': action, 'payload': payload,
                    'previous_digest': previous_digest})
    con.execute('''INSERT INTO chief_business_brief_events
                   (brief_id,action,detail_json,detail_digest,previous_digest)
                   VALUES (?,?,?,?,?)''', (brief_id, action, detail, digest, previous_digest))


def _ids(value: list[int]) -> list[int]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_ITEMS:
        raise ValueError('평가 ID는 1~10개의 목록이어야 합니다.')
    for item in value:
        _id(item, '평가')
    if len(set(value)) != len(value):
        raise ValueError('중복된 평가 ID는 허용되지 않습니다.')
    return value


def build_snapshot(con: sqlite3.Connection, evaluation_ids: list[int]) -> dict:
    """Compare immutable scenario records, without authorizing any action."""
    evaluation_ids = _ids(evaluation_ids)
    rows = []
    subjects = set()
    horizons = set()
    for evaluation_id in evaluation_ids:
        record = financial_report(con, evaluation_id)  # verifies input, result and audit
        subject = (record['subject_kind'], record['subject_id'])
        if subject in subjects:
            raise ValueError('동일 사업/후보의 중복 평가 비교는 허용되지 않습니다.')
        subjects.add(subject)
        result = record['result']
        if result['market_demand_verified'] or result['sales_verified'] or result['external_actions_executed']:
            raise ValueError('검증 상태가 예상과 다릅니다. 자동 판단을 중단합니다.')
        horizons.add(result['horizon_months'])
        scenarios = result['scenarios']
        rows.append({'evaluation_id': evaluation_id, 'subject_kind': subject[0],
                     'subject_id': subject[1], 'months': result['horizon_months'],
                     'downside_assumed_krw': scenarios['downside_25pct_units']['horizon_net_after_setup_assumed_krw'],
                     'base_assumed_krw': scenarios['base_owner_assumption']['horizon_net_after_setup_assumed_krw'],
                     'upside_assumed_krw': scenarios['upside_25pct_units']['horizon_net_after_setup_assumed_krw'],
                     'break_even_monthly_units_assumed': result['break_even_monthly_units_assumed'],
                     'assumptions_digest': _hash(record['assumptions']),
                     'result_digest': _hash(result)})
    if len(horizons) != 1:
        raise ValueError('평가 기간이 다르면 가정 손익을 직접 비교할 수 없습니다.')
    # Sorting is not a recommendation; higher assumed profits are not evidence.
    rows.sort(key=lambda row: (-row['base_assumed_krw'], row['evaluation_id']))
    return {'kind': 'unverified_owner_assumption_comparison',
            'comparison_count': len(rows), 'months': horizons.pop(), 'items': rows,
            'ranking_meaning': '입력 가정의 기준 손익 내림차순 표시일 뿐 사업 추천/선택이 아님',
            'execution_decision': 'HOLD_NO_EXECUTION', 'chief_ai_inference_performed': False,
            'market_demand_verified': False, 'sales_verified': False,
            'external_actions_executed': False, 'project_created': False,
            'missing_before_execution': ['실제 시장/경쟁 자료 독립 검증', '실제 비용/매출 자료 검증',
                                         '실제 GGUF 총괄 AI 판단 검증', '별도 관리자 실행 승인 및 안전 검사'],
            'warning': '모든 금액은 관리자 미검증 가정. 비교/확인/거부는 사업 실행 권한이 아닙니다.'}


def create(con: sqlite3.Connection, evaluation_ids: list[int], owner_note: str) -> int:
    owner_note = _label(owner_note, '검토 메모', 300)
    if con.execute('SELECT COUNT(*) FROM chief_business_briefs').fetchone()[0] >= MAX_BRIEFS:
        raise ValueError('최대 검토 기록 수를 초과했습니다.')
    snapshot = build_snapshot(con, evaluation_ids)
    text = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    if len(text) > 12000:
        raise ValueError('검토 내용이 저장 제한을 초과했습니다.')
    cur = con.execute('''INSERT INTO chief_business_briefs(snapshot_json,snapshot_digest,owner_note)
                         VALUES (?,?,?)''', (text, _hash(snapshot), owner_note))
    brief_id = int(cur.lastrowid)
    _event(con, brief_id, 'created', {'snapshot_digest': _hash(snapshot), 'owner_note': owner_note})
    return brief_id


def get(con: sqlite3.Connection, brief_id: int) -> dict:
    _id(brief_id, '검토 기록')
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM chief_business_briefs WHERE id=?', (brief_id,)).fetchone()
    if row is None:
        raise ValueError('검토 기록이 없습니다.')
    try:
        snapshot = json.loads(row['snapshot_json'])
    except (TypeError, ValueError) as exc:
        raise ValueError('검토 스냅샷 손상') from exc
    if not isinstance(snapshot, dict) or _hash(snapshot) != row['snapshot_digest']:
        raise ValueError('검토 스냅샷 무결성 오류')
    try:
        current = build_snapshot(con, [item['evaluation_id'] for item in snapshot['items']])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('원본 평가 무결성/연결 오류') from exc
    if current != snapshot:
        raise ValueError('원본 평가와 검토 스냅샷이 일치하지 않습니다.')
    events = con.execute('''SELECT * FROM chief_business_brief_events WHERE brief_id=?
                            ORDER BY id''', (brief_id,)).fetchall()
    if not events or events[0]['action'] != 'created' or len(events) > 2:
        raise ValueError('검토 감사 이력 오류')
    previous = ''
    for index, event in enumerate(events):
        if index and event['action'] not in ('acknowledged', 'rejected'):
            raise ValueError('검토 감사 상태 오류')
        try:
            payload = json.loads(event['detail_json'])
        except (TypeError, ValueError) as exc:
            raise ValueError('검토 감사 JSON 손상') from exc
        expected = _hash({'brief_id': brief_id, 'action': event['action'],
                          'payload': payload, 'previous_digest': previous})
        if event['previous_digest'] != previous or event['detail_digest'] != expected:
            raise ValueError('검토 감사 무결성 오류')
        if index == 0 and payload != {'snapshot_digest': row['snapshot_digest'],
                                     'owner_note': row['owner_note']}:
            raise ValueError('검토 생성 감사 불일치')
        if index == 1 and payload != {'review_only': True, 'external_actions_executed': False}:
            raise ValueError('검토 상태 감사 불일치')
        previous = event['detail_digest']
    return {'id': brief_id, 'owner_note': row['owner_note'], 'created_at': row['created_at'],
            'snapshot': snapshot, 'review_status': events[-1]['action'] if len(events) > 1 else 'pending',
            'external_actions_executed': False}


def review(con: sqlite3.Connection, brief_id: int, action: str) -> dict:
    if type(action) is not str or action not in ('acknowledged', 'rejected'):
        raise ValueError('검토 상태는 acknowledged/rejected만 가능합니다. 실행 승인은 불가능합니다.')
    item = get(con, brief_id)
    if item['review_status'] != 'pending':
        raise ValueError('이미 검토 처리한 기록입니다.')
    _event(con, brief_id, action, {'review_only': True, 'external_actions_executed': False})
    return get(con, brief_id)


def history(con: sqlite3.Connection, limit: int = 30) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('조회 개수는 1~100입니다.')
    ids = [row[0] for row in con.execute(
        'SELECT id FROM chief_business_briefs ORDER BY id DESC LIMIT ?', (limit,))]
    return [get(con, item) for item in ids]
