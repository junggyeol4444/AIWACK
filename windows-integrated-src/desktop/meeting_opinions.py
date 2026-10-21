"""Stage45: offline, owner-entered *attributed* meeting opinions and neutral comparison.

Opinions are not model-generated. Comparison shows counts and missing attendees;
no vote is treated as a management decision or as authorization to execute.
"""
from __future__ import annotations

import sqlite3
from desktop.meetings import _id, _text, _meeting

STANCES = ('찬성', '보류', '반대')


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS local_meeting_opinions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_id INTEGER NOT NULL REFERENCES local_ai_meetings(id) ON DELETE RESTRICT,
        agenda_id INTEGER NOT NULL REFERENCES local_meeting_agenda(id) ON DELETE RESTRICT,
        employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
        stance TEXT NOT NULL CHECK(stance IN ('찬성','보류','반대')),
        reasoning TEXT NOT NULL CHECK(length(trim(reasoning)) BETWEEN 1 AND 2000),
        evidence TEXT NOT NULL DEFAULT '' CHECK(length(evidence) <= 500),
        alternative TEXT NOT NULL DEFAULT '' CHECK(length(alternative) <= 1000),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(meeting_id,agenda_id,employee_id)
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_meeting_opinions_agenda ON local_meeting_opinions(meeting_id,agenda_id)')
    con.execute('''CREATE TRIGGER IF NOT EXISTS meeting_opinion_insert_guard
        BEFORE INSERT ON local_meeting_opinions
        WHEN NOT EXISTS (SELECT 1 FROM local_ai_meetings m WHERE m.id=NEW.meeting_id AND m.status='scheduled')
          OR NOT EXISTS (SELECT 1 FROM local_meeting_agenda a WHERE a.id=NEW.agenda_id AND a.meeting_id=NEW.meeting_id)
          OR NOT EXISTS (SELECT 1 FROM local_meeting_attendees t WHERE t.meeting_id=NEW.meeting_id AND t.employee_id=NEW.employee_id)
          OR NOT EXISTS (SELECT 1 FROM ai_employee_profiles e WHERE e.id=NEW.employee_id AND e.lifecycle='draft')
        BEGIN SELECT RAISE(ABORT,'meeting opinion requires a scheduled meeting, its agenda and an active attendee'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS meeting_opinion_update_guard
        BEFORE UPDATE ON local_meeting_opinions
        BEGIN SELECT RAISE(ABORT,'meeting opinions are immutable'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS meeting_opinion_delete_guard
        BEFORE DELETE ON local_meeting_opinions
        BEGIN SELECT RAISE(ABORT,'meeting opinions are immutable'); END''')


def add(con: sqlite3.Connection, meeting_id: int, agenda_id: int, employee_id: int,
        stance: str, reasoning: str, evidence: str = '', alternative: str = '') -> int:
    current = _meeting(con, meeting_id)
    _id(agenda_id, '안건')
    _id(employee_id, '직원')
    if current != 'scheduled':
        raise ValueError('의견은 예정 상태의 회의에만 등록할 수 있습니다.')
    if stance not in STANCES or not isinstance(stance, str):
        raise ValueError('의견은 찬성/보류/반대 중 선택하세요.')
    reason = _text(reasoning, '의견 근거', 2000)
    source = _text(evidence, '근거 출처', 500, required=False)
    option = _text(alternative, '대안', 1000, required=False)
    if not con.execute('SELECT 1 FROM local_meeting_agenda WHERE id=? AND meeting_id=?',
                       (agenda_id, meeting_id)).fetchone():
        raise ValueError('해당 회의의 안건이 아닙니다.')
    person = con.execute('''SELECT e.lifecycle FROM local_meeting_attendees a
             JOIN ai_employee_profiles e ON e.id=a.employee_id
             WHERE a.meeting_id=? AND a.employee_id=?''',(meeting_id,employee_id)).fetchone()
    if not person or person[0] != 'draft':
        raise ValueError('현재 활성 상태인 회의 참석자만 의견을 등록할 수 있습니다.')
    if con.execute('''SELECT 1 FROM local_meeting_opinions
                      WHERE meeting_id=? AND agenda_id=? AND employee_id=?''',
                   (meeting_id,agenda_id,employee_id)).fetchone():
        raise ValueError('이 참석자는 해당 안건에 이미 의견을 등록했습니다.')
    return int(con.execute('''INSERT INTO local_meeting_opinions
        (meeting_id,agenda_id,employee_id,stance,reasoning,evidence,alternative)
        VALUES (?,?,?,?,?,?,?)''',
        (meeting_id,agenda_id,employee_id,stance,reason,source,option)).lastrowid)


def list_opinions(con: sqlite3.Connection, meeting_id: int) -> list[dict]:
    _meeting(con, meeting_id)
    con.row_factory = sqlite3.Row
    return [dict(row) for row in con.execute('''SELECT o.id,o.meeting_id,o.agenda_id,a.position AS agenda_position,
        a.topic,o.employee_id,e.display_name,o.stance,o.reasoning,o.evidence,o.alternative,o.created_at,
        CASE WHEN ai.opinion_id IS NULL THEN 'owner_recorded' ELSE 'real_local_model' END AS origin,
        ai.model_call_id
        FROM local_meeting_opinions o
        JOIN local_meeting_agenda a ON a.id=o.agenda_id
        JOIN ai_employee_profiles e ON e.id=o.employee_id
        LEFT JOIN aiwack_real_meeting_model_opinions ai ON ai.opinion_id=o.id
        WHERE o.meeting_id=? ORDER BY a.position,o.employee_id''',(meeting_id,))]


def compare(con: sqlite3.Connection, meeting_id: int) -> dict:
    """Descriptive comparison; never a recommendation, quorum, approval or decision."""
    from desktop.meetings import read
    meeting = read(con, meeting_id)
    opinions = list_opinions(con, meeting_id)
    by_agenda = {}
    all_attendees = {p['employee_id']: p['display_name'] for p in meeting['attendees']}
    for opinion in opinions:
        by_agenda.setdefault(opinion['agenda_id'], []).append(opinion)
    results = []
    for agenda in meeting['agenda']:
        recorded = by_agenda.get(agenda['id'], [])
        counts = {stance: sum(o['stance']==stance for o in recorded) for stance in STANCES}
        represented = {o['employee_id'] for o in recorded}
        missing = [{'employee_id':eid,'display_name':name} for eid,name in all_attendees.items() if eid not in represented]
        results.append({'agenda_id': agenda['id'], 'position':agenda['position'], 'topic':agenda['topic'],
                        'counts': counts, 'submitted_count':len(recorded),
                        'attendee_count':len(all_attendees), 'missing_attendees':missing,
                        'has_differing_opinions':sum(counts[s]>0 for s in STANCES)>1,
                        'opinions':recorded})
    return {'meeting_id':meeting_id,'status':meeting['status'], 'agenda':results,
            'note':'의견 분포는 참고용입니다. 다수 의견도 최종 결정이나 승인으로 처리하지 않습니다.'}
