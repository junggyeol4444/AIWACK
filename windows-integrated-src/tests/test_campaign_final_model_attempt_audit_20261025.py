"""실제 총괄 최종보고 모델 호출의 실패/성공 불변 감사 계약.

임시 SQLite 호출 원본만 사용한다. 실제 GGUF 또는 Windows EXE 실검증이 아니다.
"""
from __future__ import annotations

import hashlib
import sqlite3

import pytest

from desktop import company_campaign_final_report as final_report


class _Store:
    def __init__(self, path):
        self.path = path

    def _connect(self):
        return sqlite3.connect(self.path)

    def require_permission(self, name):
        assert name == 'company:manage'


@pytest.fixture
def audit_store(tmp_path, monkeypatch):
    # Isolate only the additive final-report audit schema from existing
    # organization tables; production still initializes the full wide schema.
    monkeypatch.setattr(final_report.wide, 'initialize', lambda con: None)
    store = _Store(str(tmp_path / 'final_model_audit.sqlite'))
    with store._connect() as con:
        con.execute("""CREATE TABLE ai_model_call_history (
            id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL,
            status TEXT NOT NULL, output_chars INTEGER NOT NULL)""")
        con.executemany("""INSERT INTO ai_model_call_history
            (id,employee_id,status,output_chars) VALUES(?,?,?,?)""",
            [(21, 9, 'success', 16), (22, 9, 'success', 16),
             (23, 10, 'success', 16), (24, 9, 'failed', 16)])
        final_report.initialize(con)
    return store


def test_failed_real_model_format_is_audited_immutably(audit_store):
    raw = '부족한 총괄 응답 원문입니다'
    # The recorded output length must exactly match the actual response.
    with audit_store._connect() as con:
        con.execute('UPDATE ai_model_call_history SET output_chars=? WHERE id=21',
                    (len(raw),))
        final_report._record_final_model_attempt(
            con, 7, 9, 21, 'a' * 64, raw, parsed=False, error='형식 오류')
    rows = final_report.model_attempts(audit_store, 7)
    assert len(rows) == 1
    assert rows[0]['parsed'] == 0
    assert rows[0]['completion_sha256'] == hashlib.sha256(raw.encode()).hexdigest()
    assert rows[0]['error_reason'] == '형식 오류'
    with audit_store._connect() as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM aiwack_campaign_final_model_attempts WHERE model_call_id=21')
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("""UPDATE aiwack_campaign_final_model_attempts
                SET parsed=1 WHERE model_call_id=21""")


def test_successful_report_model_attempt_requires_sha_and_same_call(audit_store):
    raw = '최종 보고 결과가 검증된 원문'
    with audit_store._connect() as con:
        con.execute('UPDATE ai_model_call_history SET output_chars=? WHERE id=22',
                    (len(raw),))
        final_report._record_final_model_attempt(
            con, 7, 9, 22, 'b' * 64, raw,
            parsed=True, report_sha256='c' * 64)
    row = final_report.model_attempts(audit_store, 7)[0]
    assert row['parsed'] == 1 and row['report_sha256'] == 'c' * 64
    with audit_store._connect() as con:
        with pytest.raises(sqlite3.IntegrityError):
            final_report._record_final_model_attempt(
                con, 7, 9, 22, 'b' * 64, raw,
                parsed=True, report_sha256='c' * 64)


@pytest.mark.parametrize('call_id,chief', [(23, 9), (24, 9), (999, 9)])
def test_wrong_or_failed_model_call_cannot_be_recorded(audit_store, call_id, chief):
    with audit_store._connect() as con:
        with pytest.raises(ValueError, match='출처'):
            final_report._record_final_model_attempt(
                con, 7, chief, call_id, 'a' * 64, 'x' * 16,
                parsed=False, error='형식 오류')


def test_report_audit_does_not_accept_invented_success(audit_store):
    with audit_store._connect() as con:
        with pytest.raises(ValueError, match='형식'):
            final_report._record_final_model_attempt(
                con, 7, 9, 21, 'a' * 64, 'x' * 16,
                parsed=True, report_sha256='')
