"""실제 호출 이력의 응답 길이와 계획 감사가 불일치하면 저장 금지.

SQLite 단위 테스트이며 실GGUF 실행·Windows GUI 검증은 아니다.
"""
import hashlib
import sqlite3

import pytest
from desktop import company_wide_campaign as wide


class _Store:
    def __init__(self, con):
        self.con = con

    def _connect(self):
        return self.con


@pytest.fixture
def audit_store():
    con = sqlite3.connect(":memory:")
    con.execute("""CREATE TABLE ai_model_call_history(
        id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL,
        status TEXT NOT NULL, output_chars INTEGER NOT NULL)""")
    con.execute("""INSERT INTO ai_model_call_history
        (id,employee_id,status,output_chars) VALUES(7,31,'success',11)""")
    store = _Store(con)
    yield store
    con.close()


def _count(con, table):
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_plan_audit_rejects_mismatched_actual_model_output_length(audit_store):
    with pytest.raises(ValueError, match="응답 길이"):
        wide._audit_chief_plan(audit_store,1,31,7,["영업"],"single_department",
                               True,"짧음")
    assert _count(audit_store.con,"aiwack_wide_chief_plan_attempts") == 0


def test_rejection_audit_rejects_mismatched_actual_model_output_length(audit_store):
    with pytest.raises(ValueError, match="응답 길이"):
        wide._record_genuine_chief_plan_rejection(
            audit_store,1,31,7,"single_department",["영업"],"짧음","형식 오류")
    assert _count(audit_store.con,"aiwack_wide_chief_rejected_attempts") == 0


def test_plan_audit_preserves_actual_completion_hash_and_length(audit_store):
    raw = "abcdefghijk"
    wide._audit_chief_plan(audit_store,1,31,7,["영업"],"single_department",
                           True,raw)
    row = audit_store.con.execute("""SELECT output_sha256,output_chars,parsed
        FROM aiwack_wide_chief_plan_attempts WHERE model_call_id=7""").fetchone()
    assert row == (hashlib.sha256(raw.encode()).hexdigest(),len(raw),1)


@pytest.mark.parametrize("employee,status",[(99,"success"),(31,"failure")])
def test_plan_audit_rejects_wrong_employee_or_failed_call(audit_store,employee,status):
    audit_store.con.execute(
        "UPDATE ai_model_call_history SET employee_id=?,status=? WHERE id=7",
        (employee,status))
    with pytest.raises(ValueError, match="호출 ID"):
        wide._audit_chief_plan(audit_store,1,31,7,["영업"],"single_department",
                               True,"abcdefghijk")
    assert _count(audit_store.con,"aiwack_wide_chief_plan_attempts") == 0
