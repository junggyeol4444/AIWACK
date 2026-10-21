# 실제 로컬 직원 모델 기반 회의 의견. 수기 의견과 별도 모델 감사 증거 보존.
from __future__ import annotations
import hashlib
import json
import sqlite3
import threading

from desktop.meetings import _id, read as read_meeting
from desktop.meeting_opinions import add as add_opinion
from desktop.stage87_90_management import stopped
from desktop.employee_model_runtime import invoke_employee_model


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_real_meeting_model_opinions (
        opinion_id INTEGER PRIMARY KEY REFERENCES local_meeting_opinions(id) ON DELETE RESTRICT,
        model_call_id INTEGER NOT NULL UNIQUE REFERENCES ai_model_call_history(id) ON DELETE RESTRICT,
        employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id),
        output_sha256 TEXT NOT NULL CHECK(length(output_sha256)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS aiwack_meeting_model_audit_insert_guard
        BEFORE INSERT ON aiwack_real_meeting_model_opinions
        WHEN NOT EXISTS(SELECT 1 FROM local_meeting_opinions o
            JOIN ai_model_call_history h ON h.employee_id=o.employee_id
            WHERE o.id=NEW.opinion_id AND h.id=NEW.model_call_id
              AND o.employee_id=NEW.employee_id AND h.status='success' AND h.output_chars>0)
        BEGIN SELECT RAISE(ABORT,'회의 직원 의견은 성공한 동일 직원 모델 호출 증거가 필요합니다'); END''')
    for action in ('UPDATE','DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS aiwack_meeting_model_audit_no_{action.lower()}
            BEFORE {action} ON aiwack_real_meeting_model_opinions
            BEGIN SELECT RAISE(ABORT,'실제 AI 의견 감사 기록 수정·삭제 금지'); END''')


def _eligible(con, meeting_id: int, agenda_id: int, employee_id: int):
    if stopped(con):
        raise PermissionError('비상정지 중에는 AI 회의를 실행할 수 없습니다.')
    meeting=read_meeting(con, meeting_id)
    if meeting['status']!='scheduled':
        raise ValueError('예정 상태 회의에서만 직원 모델 의견을 생성할 수 있습니다.')
    agenda=next((a for a in meeting['agenda'] if a['id']==agenda_id),None)
    if agenda is None:
        raise ValueError('현재 회의에 속한 안건이 아닙니다.')
    if employee_id not in {p['employee_id'] for p in meeting['attendees'] if p['lifecycle']=='draft'}:
        raise ValueError('활성 직원 참석자가 아닙니다.')
    if con.execute('SELECT 1 FROM local_meeting_opinions WHERE meeting_id=? AND agenda_id=? AND employee_id=?',
                   (meeting_id,agenda_id,employee_id)).fetchone():
        raise ValueError('이 직원은 해당 안건에 이미 의견을 제출했습니다.')
    if con.execute('SELECT 1 FROM local_meeting_decisions WHERE agenda_id=?',(agenda_id,)).fetchone():
        raise ValueError('이미 결정된 안건에는 모델 의견을 추가하지 않습니다.')
    bound=con.execute('''SELECT e.display_name,a.model_id FROM ai_employee_profiles e
        JOIN ai_employee_model_assignments a ON a.employee_id=e.id
        WHERE e.id=? AND e.lifecycle='draft' ''',(employee_id,)).fetchone()
    if not bound:
        raise ValueError('참석 직원에게 실제 로컬 AI 모델 배정이 필요합니다.')
    return meeting,agenda,int(bound[1])


def _parse_reply(raw: str):
    if not isinstance(raw,str) or not 2<=len(raw.strip())<=5000:
        raise ValueError('로컬 직원 모델의 의견 응답이 비었거나 제한을 넘었습니다.')
    value=raw.strip()
    if value.startswith('```json') and value.endswith('```'):
        value=value[7:-3].strip()
    try:
        item=json.loads(value)
    except (TypeError,ValueError) as exc:
        raise ValueError('로컬 모델 응답은 지정된 JSON 한 개여야 합니다.') from exc
    if not isinstance(item,dict) or set(item)-{'stance','reasoning','alternative'}:
        raise ValueError('입장·근거·대안 외의 키는 기록하지 않습니다.')
    stance=item.get('stance')
    reason=item.get('reasoning')
    alternative=item.get('alternative','')
    if stance not in ('찬성','보류','반대') or not isinstance(reason,str) or not 1<=len(reason.strip())<=2000:
        raise ValueError('의견은 찬성/보류/반대 및 1~2000자 근거가 필수입니다.')
    if not isinstance(alternative,str) or len(alternative)>1000:
        raise ValueError('대안은 1000자 이하 문자열이어야 합니다.')
    return stance,reason.strip(),alternative.strip()


def run_one(store, meeting_id: int, agenda_id: int, employee_id: int,
            *, cancel: threading.Event | None=None, timeout: int=90) -> dict:
    store.require_permission('company:manage')
    store.require_permission('agents:manage')
    for value,label in ((meeting_id,'회의'),(agenda_id,'안건'),(employee_id,'직원')):
        _id(value,label)
    if cancel is not None and cancel.is_set():
        raise InterruptedError('취소된 AI 회의 모델 요청은 시작하지 않습니다.')
    with store._connect() as con:
        initialize(con)
        meeting,agenda,model_id=_eligible(con,meeting_id,agenda_id,employee_id)
    prompt=(
        '당신은 소유자가 실제 로컬 모델을 배정한 AI 직원입니다. 독립적 의견만 작성하세요. '
        '근거가 부족하면 보류를 선택하세요. 실제 외부 거래·계약·결제·도구 실행은 하지 마세요. '
        '단일 JSON 객체로만 응답: '
        '{"stance":"찬성 또는 보류 또는 반대","reasoning":"구체적인 근거","alternative":"선택 대안"}. '
        '조사하지 않은 외부 사실을 확인했다고 주장하지 마세요.\n'
        '회의: '+str(meeting['title'])[:120]+'\n'
        '목적: '+str(meeting['purpose'])[:450]+'\n'
        '안건: '+str(agenda['topic'])[:400]
    )
    raw,call_id=invoke_employee_model(store,employee_id,prompt,timeout=timeout,cancel=cancel,
                                      include_call_id=True)
    stance,reason,alternative=_parse_reply(raw)
    if cancel is not None and cancel.is_set():
        raise InterruptedError('취소된 모델 의견은 저장하지 않습니다.')
    store.require_permission('company:manage')
    store.require_permission('agents:manage')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        _,_,bound_model=_eligible(con,meeting_id,agenda_id,employee_id)
        if bound_model!=model_id:
            raise PermissionError('실행 중 직원 로컬 모델 배정이 변경되었습니다.')
        row=con.execute('''SELECT employee_id,model_id,status,output_chars
                           FROM ai_model_call_history WHERE id=?''',(call_id,)).fetchone()
        if not row or row[0]!=employee_id or row[1]!=model_id or row[2]!='success' or row[3]<=0:
            raise PermissionError('동일 직원의 실제 성공 모델 호출 감사를 확인할 수 없습니다.')
        opinion_id=add_opinion(con,meeting_id,agenda_id,employee_id,stance,reason,
                              '로컬 AI 모델 생성(외부 사실 별도 미검증)',alternative)
        con.execute('''INSERT INTO aiwack_real_meeting_model_opinions
            (opinion_id,model_call_id,employee_id,output_sha256) VALUES(?,?,?,?)''',
            (opinion_id,call_id,employee_id,hashlib.sha256(raw.encode('utf8')).hexdigest()))
    return dict(opinion_id=opinion_id,model_call_id=call_id,meeting_id=meeting_id,
                employee_id=employee_id,stance=stance,origin='real_local_model',
                decision_created=False,external_action_performed=False)


def report(store, meeting_id: int) -> list[dict]:
    store.require_permission('agents:manage')
    _id(meeting_id,'회의')
    with store._connect() as con:
        initialize(con)
        return [dict(opinion_id=int(o),employee_id=int(e),model_call_id=int(c),
                     output_sha256=d,created_at=t,external_facts_verified=False)
                for o,e,c,d,t in con.execute('''SELECT a.opinion_id,a.employee_id,
                    a.model_call_id,a.output_sha256,a.created_at
                    FROM aiwack_real_meeting_model_opinions a
                    JOIN local_meeting_opinions o ON o.id=a.opinion_id
                    WHERE o.meeting_id=? ORDER BY a.opinion_id''',(meeting_id,))]
