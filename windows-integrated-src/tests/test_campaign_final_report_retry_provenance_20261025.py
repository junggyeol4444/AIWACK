"""최종 총괄 실모델 성공 감사 연결 검증.

임시 SQLite 단위 계약만 검증하며 실제 GGUF/Windows GUI 실행이 아니다.
"""
import sqlite3

import pytest

from desktop import company_campaign_final_report as final_report


@pytest.fixture
def ledger():
    con = sqlite3.connect(':memory:')
    con.execute("""CREATE TABLE aiwack_campaign_final_model_attempts (
        campaign_id INTEGER, chief_employee_id INTEGER, model_call_id INTEGER,
        evidence_sha256 TEXT, completion_sha256 TEXT, completion_chars INTEGER,
        parsed INTEGER, report_sha256 TEXT, error_reason TEXT
    )""")
    yield con
    con.close()


def _record(con, *, campaign=7, chief=9, call=21, seal='a' * 64,
            raw='b' * 64, chars=33, parsed=1, digest='c' * 64, error=''):
    con.execute("""INSERT INTO aiwack_campaign_final_model_attempts
        (campaign_id, chief_employee_id, model_call_id, evidence_sha256,
         completion_sha256, completion_chars, parsed, report_sha256, error_reason)
         VALUES (?,?,?,?,?,?,?,?,?)""",
        (campaign, chief, call, seal, raw, chars, parsed, digest, error))


def _verify(con):
    return final_report._verify_final_attempt_link(
        con, 7, 9, 21, 'a' * 64, 'c' * 64, 33)


def test_valid_genuine_model_call_audit_is_bound_to_final_report(ledger):
    _record(ledger)
    assert _verify(ledger) is None


def test_missing_final_model_attempt_is_not_reconstructed(ledger):
    with pytest.raises(ValueError, match='누락'):
        _verify(ledger)


@pytest.mark.parametrize('field,wrong', [
    ('campaign', 8), ('chief', 10), ('seal', 'd' * 64),
    ('raw', 'not-a-digest'), ('chars', 34), ('parsed', 0),
    ('digest', 'e' * 64), ('error', '이전 형식 실패'),
])
def test_final_report_rejects_changed_immutable_attempt_fields(ledger, field, wrong):
    fields = dict(campaign=7, chief=9, call=21, seal='a' * 64,
                  raw='b' * 64, chars=33, parsed=1, digest='c' * 64, error='')
    fields[field] = wrong
    _record(ledger, **fields)
    with pytest.raises(ValueError, match='불일치'):
        _verify(ledger)


def test_final_report_rejects_ambiguous_duplicate_model_attempt(ledger):
    _record(ledger)
    _record(ledger)
    with pytest.raises(ValueError, match='중복'):
        _verify(ledger)


def test_final_report_rejects_boolean_model_call_length(ledger):
    _record(ledger, chars=True)
    with pytest.raises(ValueError, match='불일치'):
        _verify(ledger)
