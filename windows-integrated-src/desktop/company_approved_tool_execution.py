"""기존 Windows EXE의 승인형 로컬 읽기 도구 실행·SQLite 증빙.

도구 등록/승인만으로 자동 실행하지 않는다. 소유자가 선택 요청을
명시적으로 실행할 때 허용된 내장 읽기 도구만 실제 SQLite 조회한다.
외부 파일, 명령, 네트워크, 결제 및 AI 임의 코드 실행은 제공하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from desktop import tool_approvals
from desktop.stage87_90_management import stopped

READ_ONLY_TOOLS = frozenset({'local_company_reader', 'local_goals_reader'})


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_approved_tool_executions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL UNIQUE REFERENCES tool_use_requests(id),
        employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id),
        tool_key TEXT NOT NULL CHECK(tool_key IN ('local_company_reader','local_goals_reader')),
        result_json TEXT NOT NULL CHECK(length(result_json) BETWEEN 2 AND 4096),
        result_sha256 TEXT NOT NULL CHECK(length(result_sha256)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    for op in ('UPDATE', 'DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS aiwack_tool_executions_no_{op.lower()}
            BEFORE {op} ON aiwack_approved_tool_executions BEGIN
            SELECT RAISE(ABORT,'승인형 읽기 도구 실행 기록은 변경할 수 없습니다'); END''')


def _payload(con: sqlite3.Connection, tool_key: str) -> dict:
    if tool_key == 'local_company_reader':
        row=con.execute('SELECT name,description,mission FROM company_profile WHERE id=1').fetchone()
        tasks=con.execute('''SELECT status,COUNT(*) FROM company_tasks
            GROUP BY status ORDER BY status''').fetchall()
        return {'tool':'local_company_reader', 'company_name':str(row[0])[:120] if row else '',
                'mission':str(row[2])[:200] if row else '',
                'tasks_by_state':{str(k):int(v) for k,v in tasks},
                'real_revenue_verified':False}
    if tool_key == 'local_goals_reader':
        goals=con.execute('''SELECT id,title,status FROM company_goals
            ORDER BY id DESC LIMIT 10''').fetchall()
        return {'tool':'local_goals_reader',
                'goals':[{'id':int(gid),'title':str(title)[:120],
                          'status':str(state)[:32]} for gid,title,state in goals],
                'owner_approval_for_external_action':True}
    raise PermissionError('허용되지 않은 로컬 읽기 도구입니다.')


def execute(store, request_id: int) -> dict:
    """단일 SQLite 트랜잭션에서 현재 권한 재검사→실제 조회→감사 저장.

    승인 철회/비상정지/다른 EXE 동시 실행 시 fail-closed.
    요청당 한 번만 실행하고 재시도는 이전 증빙을 반환한다.
    """
    store.require_permission('company:manage')
    if type(request_id) is not int or request_id < 1:
        raise ValueError('도구 실행 요청 번호가 올바르지 않습니다.')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        if stopped(con):
            raise PermissionError('비상정지 중에는 도구를 실행할 수 없습니다.')
        request=tool_approvals.get_request(con,request_id)
        if request['tool_key'] not in READ_ONLY_TOOLS:
            raise PermissionError('현재 실제 실행을 지원하는 도구는 회사/목표 로컬 읽기뿐입니다.')
        current=tool_approvals.preflight(con,request_id)
        if not current['allowed']:
            raise PermissionError('현재 권한·승인 검증 실패: '+current['reason'])
        old=con.execute('''SELECT id,result_json,result_sha256
            FROM aiwack_approved_tool_executions WHERE request_id=?''',(request_id,)).fetchone()
        if old:
            payload=old[1]
            if hashlib.sha256(payload.encode('utf-8')).hexdigest()!=old[2]:
                raise ValueError('기존 도구 실행 결과의 무결성 오류')
            return {'execution_id':int(old[0]),'request_id':request_id,
                    'result':json.loads(payload),'sha256':old[2],
                    'already_executed':True,'external_action_performed':False}
        data=_payload(con,request['tool_key'])
        payload=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        if len(payload)>4096:
            raise ValueError('로컬 읽기 결과가 감사 저장 한도를 초과했습니다.')
        digest=hashlib.sha256(payload.encode('utf-8')).hexdigest()
        cur=con.execute('''INSERT INTO aiwack_approved_tool_executions(
            request_id,employee_id,tool_key,result_json,result_sha256)
            VALUES(?,?,?,?,?)''',(request_id,request['employee_id'],request['tool_key'],payload,digest))
        return {'execution_id':int(cur.lastrowid),'request_id':request_id,
                'result':data,'sha256':digest,'already_executed':False,
                'external_action_performed':False}


def history(store, limit: int=30) -> list[dict]:
    store.require_permission('company:manage')
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError('실제 도구 실행 기록은 1~100건 조회할 수 있습니다.')
    with store._connect() as con:
        initialize(con)
        rows=con.execute('''SELECT id,request_id,employee_id,tool_key,
            result_json,result_sha256,created_at FROM aiwack_approved_tool_executions
            ORDER BY id DESC LIMIT ?''',(limit,)).fetchall()
    out=[]
    for rid,request_id,employee_id,key,payload,digest,created in rows:
        if hashlib.sha256(payload.encode('utf-8')).hexdigest()!=digest:
            raise ValueError('도구 실행 감사 결과 무결성 오류')
        out.append({'execution_id':int(rid),'request_id':int(request_id),
                    'employee_id':int(employee_id),'tool_key':key,
                    'sha256':digest,'created_at':created,'result':json.loads(payload),
                    'external_action_performed':False})
    return out
