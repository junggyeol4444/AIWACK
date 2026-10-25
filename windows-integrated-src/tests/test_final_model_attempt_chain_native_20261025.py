"""기존 Windows 네이티브 총괄 모델 시도/최종보고 감사 연결의 SQLite 계약 검사.

합성 SQLite 데이터만 사용하며 실제 GGUF 실행, 물리 GUI, T01~T20 검증이 아니다.
"""
import hashlib
import sqlite3

import pytest

from desktop import company_campaign_final_report as final


class _Store:
    def __init__(self, db):
        self.db = str(db)

    def _connect(self):
        return sqlite3.connect(self.db)

    def require_permission(self, permission):
        assert permission == 'company:manage'


@pytest.fixture
def audit(tmp_path, monkeypatch):
    monkeypatch.setattr(final.wide, 'initialize', lambda con: None)
    monkeypatch.setattr(final, '_complete_evidence', lambda store, cid: ({}, 'a' * 64))
    store = _Store(tmp_path / 'real_model_audit.sqlite')
    with store._connect() as con:
        con.execute('CREATE TABLE ai_employee_profiles (id INTEGER PRIMARY KEY)')
        con.execute('INSERT INTO ai_employee_profiles(id) VALUES (9)')
        con.execute('''CREATE TABLE aiwack_wide_campaigns
                       (id INTEGER PRIMARY KEY, chief_employee_id INTEGER, state TEXT)''')
        con.execute("INSERT INTO aiwack_wide_campaigns VALUES (7,9,'approved')")
        con.execute('''CREATE TABLE ai_model_call_history (
            id INTEGER PRIMARY KEY, employee_id INTEGER, status TEXT,
            output_chars INTEGER, model_id TEXT)''')
        final.initialize(con)
    return store


def _attempt(store, call_id=21, raw='실제 총괄 응답', parsed=False,
             error='형식 부족', body=None):
    with store._connect() as con:
        con.execute('''INSERT INTO ai_model_call_history
            (id,employee_id,status,output_chars,model_id)
            VALUES (?,?,?,?,?)''', (call_id,9,'success',len(raw),'local-gguf'))
        digest = hashlib.sha256((body or '').encode()).hexdigest() if parsed else ''
        final._record_final_model_attempt(
            con,7,9,call_id,'a' * 64,raw,parsed=parsed,
            report_sha256=digest,error='' if parsed else error)
        if parsed:
            con.execute('''INSERT INTO aiwack_campaign_final_reports
                (campaign_id,chief_employee_id,chief_model_call_id,
                 evidence_sha256,report_body,report_sha256)
                VALUES (?,?,?,?,?,?)''',
                (7,9,call_id,'a' * 64,body,digest))


def test_no_model_call_does_not_claim_success(audit):
    state = final.inspect_final_model_attempt_chain(audit,7)
    assert state['status'] == 'no_model_attempt'
    assert state['successful_report_count'] == 0
    assert state['independent_gguf_binary_verified'] is False


def test_failed_real_model_format_attempt_is_preserved_and_read_only(audit):
    _attempt(audit)
    first = final.inspect_final_model_attempt_chain(audit,7)
    second = final.inspect_final_model_attempt_chain(audit,7)
    assert first == second
    assert first['status'] == 'format_failures_only'
    assert first['failed_format_count'] == 1
    assert len(first['attempts_sha256']) == 64


def test_failed_then_real_successful_report_chain(audit):
    _attempt(audit,call_id=21,raw='잘못된 실제 출력')
    _attempt(audit,call_id=22,raw='총괄 최종 응답',parsed=True,
             body='실제 모델이 작성한 총괄 최종보고 본문')
    state = final.inspect_final_model_attempt_chain(audit,7)
    assert state['status'] == 'report_saved'
    assert state['attempt_count'] == 2
    assert state['failed_format_count'] == 1
    assert state['successful_report_count'] == 1
    assert state['physical_windows_exe_verified'] is False


def test_attempt_chain_rejects_changed_original_call_length(audit):
    _attempt(audit)
    with audit._connect() as con:
        con.execute('UPDATE ai_model_call_history SET output_chars=1 WHERE id=21')
    with pytest.raises(ValueError,match='원본 불일치'):
        final.inspect_final_model_attempt_chain(audit,7)


def test_attempt_chain_rejects_missing_success_audit_for_report(audit):
    with audit._connect() as con:
        con.execute('''INSERT INTO aiwack_campaign_final_reports
            (campaign_id,chief_employee_id,chief_model_call_id,
             evidence_sha256,report_body,report_sha256)
            VALUES (?,?,?,?,?,?)''',(7,9,99,'a'*64,'본문',
                hashlib.sha256('본문'.encode()).hexdigest()))
    with pytest.raises(ValueError,match='연결 불일치'):
        final.inspect_final_model_attempt_chain(audit,7)


def test_attempt_chain_rejects_report_body_tampering(audit):
    _attempt(audit,parsed=True,body='진짜 총괄 본문')
    with audit._connect() as con:
        # Production immutable trigger blocks this edit. The fixture checks
        # fail-closed behavior even if the database was altered externally.
        con.execute('DROP TRIGGER aiwack_campaign_final_reports_immutable_update')
        con.execute("UPDATE aiwack_campaign_final_reports SET report_body='변조' WHERE campaign_id=7")
    with pytest.raises(ValueError,match='연결 불일치'):
        final.inspect_final_model_attempt_chain(audit,7)


def test_attempt_chain_rejects_boolean_campaign_id(audit):
    with pytest.raises(ValueError,match='번호'):
        final.inspect_final_model_attempt_chain(audit,True)
