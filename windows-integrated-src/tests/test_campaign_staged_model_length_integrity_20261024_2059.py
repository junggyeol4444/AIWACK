"""실제 GGUF 총괄 계획 단계별 감사의 모델 응답 길이·SHA 형식 계약 검사.

합성 SQLite 감사 레코드만 사용한다. 실제 모델 실행, 승인, Windows EXE 검증은 아니다.
"""
import hashlib
import json
import sqlite3

import pytest

from desktop import company_wide_campaign as wide


def _staged_connection(*, model_chars=10, plan_chars=10, digest=None):
    con = sqlite3.connect(":memory:")
    con.execute("""CREATE TABLE aiwack_wide_chief_group_staging (
        source_task_id INTEGER, group_start INTEGER, source_fingerprint TEXT,
        roster_sha256 TEXT, chief_employee_id INTEGER, chief_model_id INTEGER,
        group_json TEXT, group_sha256 TEXT)""")
    con.execute("""CREATE TABLE ai_model_call_history (
        id INTEGER, employee_id INTEGER, model_id INTEGER, status TEXT,
        output_chars INTEGER)""")
    con.execute("""CREATE TABLE aiwack_wide_chief_rejected_attempts (
        model_call_id INTEGER)""")
    con.execute("""CREATE TABLE aiwack_wide_chief_plan_attempts (
        model_call_id INTEGER, source_task_id INTEGER, chief_employee_id INTEGER,
        department_names TEXT, attempt_kind TEXT, parsed INTEGER,
        output_chars INTEGER, output_sha256 TEXT)""")
    entries = [{
        "department_id": 10, "department": "기획", "manager": 31,
        "staff": 32, "title": "실제 계획", "instruction": "승인 전 내부 업무 계획 검토",
        "chief_call_id": 100,
    }]
    raw = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    con.execute("""INSERT INTO aiwack_wide_chief_group_staging
        VALUES (1,0,'source','roster',31,9,?,?)""",
        (raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()))
    con.execute("INSERT INTO ai_model_call_history VALUES (100,31,9,'success',?)",
                (model_chars,))
    con.execute("""INSERT INTO aiwack_wide_chief_plan_attempts
        VALUES (100,1,31,'기획','single_department',1,?,?)""",
        (plan_chars, digest if digest is not None else "a" * 64))
    return con


def _read_staged(con):
    return wide._verified_staged_group(
        con, 1, 0, "source", "roster", 31, 9,
        [(10, "기획", 31, 32)])


def test_matching_model_call_length_and_digest_preserves_staged_plan():
    con = _staged_connection()
    try:
        parsed, calls = _read_staged(con)
        assert calls == {"기획": 100}
        assert parsed["기획"][0] == "실제 계획"
    finally:
        con.close()


@pytest.mark.parametrize("model_chars,plan_chars,digest", [
    (10, 9, "a" * 64),
    (10, 11, "a" * 64),
    (10, None, "a" * 64),
    (0, 0, "a" * 64),
    (10, 10, "a" * 63),
    (10, 10, "Z" * 64),
])
def test_staged_plan_rejects_missing_mismatched_or_malformed_call_provenance(
        model_chars, plan_chars, digest):
    con = _staged_connection(model_chars=model_chars,
                             plan_chars=plan_chars, digest=digest)
    try:
        with pytest.raises(ValueError, match="감사|불일치"):
            _read_staged(con)
    finally:
        con.close()
