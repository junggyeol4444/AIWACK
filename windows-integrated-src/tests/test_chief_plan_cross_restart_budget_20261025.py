"""15부서 총괄 실제 GGUF 계획의 누적 형식 재시도 상한 계약.

SQLite 임시 원본으로만 검증하도록 작성. 실제 GGUF/Windows EXE 검증이 아니다.
전체 개발 완료 후 전체 통합검증 단계에서 기존 테스트와 함께 실행한다.
"""
from __future__ import annotations

import sqlite3

import pytest

from desktop import company_wide_campaign as wide


class AuditStore:
    def __init__(self, path):
        self.path = str(path)

    def _connect(self):
        return sqlite3.connect(self.path)


@pytest.fixture
def store(tmp_path):
    db = AuditStore(tmp_path / "chief-retry.sqlite3")
    with db._connect() as con:
        con.execute("""CREATE TABLE ai_model_call_history (
            id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL,
            model_id INTEGER NOT NULL, status TEXT NOT NULL,
            output_chars INTEGER NOT NULL)""")
        wide.initialize(con)
    return db


def _call(store, call_id, *, kind="three_departments",
          names=("기획부", "개발부", "재무부"), parsed=False, chief=31, model=7):
    raw = "실제 GGUF 대신 계약만 검사하는 테스트 입력"
    with store._connect() as con:
        con.execute("""INSERT INTO ai_model_call_history
            (id,employee_id,model_id,status,output_chars)
            VALUES(?,?,?,'success',?)""", (call_id, chief, model, len(raw)))
    wide._audit_chief_plan(
        store, 11, chief, call_id, names, kind, parsed, raw,
        "" if parsed else ValueError("실제 모델 형식 오류"),
        prompt="계약 테스트 프롬프트")


def _budget(store, *, kind="three_departments",
            names=("기획부", "개발부", "재무부"), chief=31, model=7):
    return wide._genuine_chief_format_retry_budget(
        store, 11, chief, model, names, kind)


def test_group_retry_count_is_durable_across_separate_store_instances(store):
    assert _budget(store)["remaining_real_model_format_attempts"] == 3
    _call(store, 101)
    second = AuditStore(store.path)
    assert _budget(second)["failed_format_count"] == 1
    assert _budget(second)["remaining_real_model_format_attempts"] == 2
    _call(second, 102)
    _call(second, 103)
    assert _budget(AuditStore(store.path))["remaining_real_model_format_attempts"] == 0


def test_single_department_has_independent_durable_retry_budget(store):
    _call(store, 201, kind="single_department", names=("기획부",))
    _call(store, 202, kind="three_departments")
    assert _budget(store, kind="single_department", names=("기획부",))[
        "remaining_real_model_format_attempts"] == 2
    assert _budget(store, kind="single_department", names=("개발부",))[
        "remaining_real_model_format_attempts"] == 3
    assert _budget(store)["remaining_real_model_format_attempts"] == 2


def test_successful_model_parse_without_staging_blocks_reinvocation(store):
    _call(store, 301, parsed=True)
    with pytest.raises(ValueError, match="재호출 금지"):
        _budget(AuditStore(store.path))


def test_immutable_failure_mirror_missing_blocks_reinvocation(store):
    raw = "모델 원문은 외부로 유출하지 않음"
    with store._connect() as con:
        con.execute("""INSERT INTO ai_model_call_history
            (id,employee_id,model_id,status,output_chars)
            VALUES(401,31,7,'success',?)""", (len(raw),))
        con.execute("""INSERT INTO aiwack_wide_chief_plan_attempts
            (source_task_id,chief_employee_id,model_call_id,department_names,
             attempt_kind,parsed,error_kind,output_sha256,output_chars)
            VALUES(11,31,401,'기획부,개발부,재무부','three_departments',0,
                   '형식 오류',?,?)""", (__import__('hashlib').sha256(raw.encode()).hexdigest(), len(raw)))
    with pytest.raises(ValueError, match="이중 감사"):
        _budget(store)


def test_changed_model_or_chief_cannot_reset_prior_attempts(store):
    _call(store, 501)
    with pytest.raises(ValueError, match="출처"):
        _budget(store, model=8)
    with pytest.raises(ValueError, match="담당 총괄"):
        _budget(store, chief=32)


def test_invalid_request_is_rejected_before_model_or_external_action(store):
    with pytest.raises(ValueError, match="요청"):
        _budget(store, kind="three_departments", names=("기획부",))
    with pytest.raises(ValueError, match="요청"):
        _budget(store, kind="single_department", names=("기획부", "개발부"))
