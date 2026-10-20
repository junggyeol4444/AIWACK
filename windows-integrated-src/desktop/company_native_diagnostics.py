"""소유자 명시 승인 후 Windows 자체 명령으로 운영체제 버전을 조회한다.

임의 명령·인수·경로·네트워크·금전 작업은 허용하지 않는다. 요청별 1회만
실행하며, 다중 EXE 창과 중단된 실행의 재호출을 SQLite에서 차단한다.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import uuid

from desktop import tool_approvals
from desktop.stage87_90_management import stopped

TOOL_KEY = 'local_windows_version_reader'


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_native_tool_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL UNIQUE REFERENCES tool_use_requests(id),
        employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id),
        tool_key TEXT NOT NULL CHECK(tool_key='local_windows_version_reader'),
        token TEXT NOT NULL CHECK(length(token)=32),
        state TEXT NOT NULL CHECK(state IN ('running','success','failed','cancelled')),
        result_json TEXT NOT NULL DEFAULT '',
        result_sha256 TEXT NOT NULL DEFAULT '',
        error_code TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at TEXT,
        CHECK((state='running' AND result_json='' AND result_sha256='' AND finished_at IS NULL)
           OR (state='success' AND length(result_json) BETWEEN 2 AND 4096
               AND length(result_sha256)=64 AND finished_at IS NOT NULL)
           OR (state IN ('failed','cancelled') AND result_json=''
               AND result_sha256='' AND length(error_code)>0 AND finished_at IS NOT NULL))
    )''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS aiwack_native_tool_no_delete
        BEFORE DELETE ON aiwack_native_tool_runs BEGIN
        SELECT RAISE(ABORT,'Windows 도구 감사 기록 삭제 금지'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS aiwack_native_tool_update_guard
        BEFORE UPDATE ON aiwack_native_tool_runs BEGIN
        SELECT RAISE(ABORT,'실행 중인 감사 기록만 한 번 완료 처리 가능') WHERE
          OLD.state!='running' OR NEW.state NOT IN ('success','failed','cancelled')
          OR OLD.id!=NEW.id OR OLD.request_id!=NEW.request_id
          OR OLD.employee_id!=NEW.employee_id OR OLD.tool_key!=NEW.tool_key
          OR OLD.token!=NEW.token OR OLD.created_at!=NEW.created_at
          OR NEW.finished_at IS NULL; END''')


def _run_windows_version() -> str:
    """고정된 Windows 기본 명령만 실행한다. 사용자 입력은 명령에 사용하지 않는다."""
    if os.name != 'nt':
        raise OSError('실제 Windows 환경에서만 운영체제 명령을 실행합니다.')
    # 환경변수 SystemRoot는 변조될 수 있으므로 Windows API가 제공하는
    # 실제 시스템 디렉터리에서만 cmd.exe를 선택한다.
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if not 0 < length < len(buffer):
        raise OSError('Windows 시스템 디렉터리를 확인할 수 없습니다.')
    exe = Path(buffer.value) / 'cmd.exe'
    if not exe.is_file():
        raise OSError('Windows 기본 cmd.exe를 찾을 수 없습니다.')
    proc = subprocess.run([str(exe), '/d', '/c', 'ver'], shell=False,
                          capture_output=True, text=True, errors='replace',
                          timeout=8, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if proc.returncode != 0:
        raise RuntimeError('Windows 버전 조회 명령이 실패했습니다.')
    value = proc.stdout.strip()
    if not value or len(value) > 1024:
        raise RuntimeError('Windows 버전 조회 결과가 없거나 너무 깁니다.')
    return value


def _row_to_result(row, already: bool) -> dict:
    rid, req, state, payload, digest, error = row
    if state == 'success':
        if hashlib.sha256(payload.encode('utf-8')).hexdigest() != digest:
            raise ValueError('Windows 도구 실행 감사 SHA256 불일치')
        return {'execution_id': int(rid), 'request_id': int(req), 'state': state,
                'result': json.loads(payload), 'sha256': digest,
                'already_executed': already, 'external_action_performed': True}
    raise RuntimeError(f'요청 #{req}은 {state} 상태입니다. 자동 재실행하지 않습니다. ({error})')


def execute(store, request_id: int) -> dict:
    store.require_permission('company:manage')
    if type(request_id) is not int or request_id < 1:
        raise ValueError('실제 Windows 도구 요청 번호가 올바르지 않습니다.')
    token = uuid.uuid4().hex
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        if stopped(con):
            raise PermissionError('비상정지 중에는 Windows 도구를 실행하지 않습니다.')
        request = tool_approvals.get_request(con, request_id)
        if request['tool_key'] != TOOL_KEY:
            raise PermissionError('선택 요청은 Windows 운영체제 버전 조회 도구가 아닙니다.')
        verdict = tool_approvals.preflight(con, request_id)
        if not verdict['allowed']:
            raise PermissionError('직원 도구 권한·승인 재검사 실패: ' + verdict['reason'])
        row = con.execute('''SELECT id,request_id,state,result_json,result_sha256,error_code
                             FROM aiwack_native_tool_runs WHERE request_id=?''', (request_id,)).fetchone()
        if row:
            return _row_to_result(row, True)
        cur = con.execute('''INSERT INTO aiwack_native_tool_runs
            (request_id,employee_id,tool_key,token,state) VALUES(?,?,?,?, 'running')''',
            (request_id, request['employee_id'], TOOL_KEY, token))
        execution_id = int(cur.lastrowid)

    # DB 쓰기 잠금을 풀고 실행. 명령 실행 시간에는 다른 창이 비상정지를 걸 수 있다.
    result = None
    failure = ''
    try:
        result = {'tool': TOOL_KEY, 'windows_version': _run_windows_version(),
                  'read_only': True, 'network_used': False,
                  'payment_performed': False}
    except subprocess.TimeoutExpired:
        failure = 'timeout'
    except Exception as exc:
        # 예외 발생 시에도 running 상태를 실패 감사로 확정한다.
        failure = type(exc).__name__

    try:
        store.require_permission('company:manage')
        session_active = True
    except PermissionError:
        session_active = False

    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        if not session_active:
            state, failure = 'cancelled', 'owner_session_ended'
        elif stopped(con):
            state, failure = 'cancelled', 'emergency_stop'
        else:
            try:
                verdict = tool_approvals.preflight(con, request_id)
                state = 'success' if verdict['allowed'] and not failure else 'failed'
                if not verdict['allowed']:
                    state, failure = 'cancelled', 'approval_or_permission_revoked'
            except (ValueError, PermissionError):
                state, failure = 'cancelled', 'approval_or_permission_revoked'
        payload = json.dumps(result, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':')) if state == 'success' else ''
        digest = hashlib.sha256(payload.encode('utf-8')).hexdigest() if payload else ''
        if len(payload) > 4096:
            state, payload, digest, failure = 'failed', '', '', 'result_too_large'
        updated = con.execute('''UPDATE aiwack_native_tool_runs
            SET state=?,result_json=?,result_sha256=?,error_code=?,finished_at=CURRENT_TIMESTAMP
            WHERE id=? AND token=? AND state='running' ''',
            (state, payload, digest, failure, execution_id, token))
        if updated.rowcount != 1:
            raise RuntimeError('실행 소유권이 변경되어 결과를 저장하지 않았습니다.')
        row = con.execute('''SELECT id,request_id,state,result_json,result_sha256,error_code
                             FROM aiwack_native_tool_runs WHERE id=?''', (execution_id,)).fetchone()
    # 실패/취소 감사 기록을 COMMIT한 후 예외를 반환한다.
    return _row_to_result(row, False)


def history(store, limit: int = 30) -> list[dict]:
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Windows 도구 감사는 1~100건만 조회합니다.')
    with store._connect() as con:
        initialize(con)
        rows = con.execute('''SELECT id,request_id,employee_id,tool_key,state,
                                   result_json,result_sha256,error_code,created_at,finished_at
                            FROM aiwack_native_tool_runs ORDER BY id DESC LIMIT ?''', (limit,)).fetchall()
    output = []
    for rid, req, emp, key, state, payload, digest, error, created, finished in rows:
        if state == 'success' and hashlib.sha256(payload.encode('utf-8')).hexdigest() != digest:
            raise ValueError('Windows 도구 실행 감사 SHA256 불일치')
        output.append({'execution_id': int(rid), 'request_id': int(req), 'employee_id': int(emp),
                       'tool_key': key, 'state': state, 'sha256': digest,
                       'result': json.loads(payload) if payload else None,
                       'error_code': error, 'created_at': created, 'finished_at': finished})
    return output
