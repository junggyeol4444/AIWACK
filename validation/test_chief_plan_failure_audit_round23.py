"""Windows 30-step failure metadata tests, without claiming real GGUF inference."""
import hashlib
import json
import sqlite3

import pytest
from validation.windows_real_30_step_campaign_e2e import read_failed_chief_plan_audit


def _db(tmp_path):
    db=tmp_path/'disposable-audit.sqlite3'
    with sqlite3.connect(db) as con:
        con.execute('''CREATE TABLE aiwack_wide_chief_rejected_attempts(
            id INTEGER PRIMARY KEY,
            model_call_id INTEGER,
            attempt_kind TEXT,
            requested_departments TEXT,
            output_sha256 TEXT,
            output_chars INTEGER,
            error_reason TEXT)''')
        output='unstructured real-model response, keep private'
        con.execute('''INSERT INTO aiwack_wide_chief_rejected_attempts
            VALUES(1,12,'single_department',?,?,?,?)''',(
            json.dumps(['고객지원부'],ensure_ascii=False),
            hashlib.sha256(output.encode()).hexdigest(),len(output),
            '부서·제목·지시 형식 오류'))
    return db


def test_missing_model_audit_is_not_success(tmp_path):
    assert read_failed_chief_plan_audit(tmp_path/'nonexistent.sqlite3')==[]
    blank=tmp_path/'blank.sqlite3'
    with sqlite3.connect(blank):pass
    assert read_failed_chief_plan_audit(blank)==[]


def test_real_call_metadata_can_be_saved_without_model_raw_text(tmp_path):
    db=_db(tmp_path)
    records=read_failed_chief_plan_audit(db)
    assert len(records)==1
    assert records[0]['real_model_call_id']==12
    assert records[0]['kind']=='single_department'
    assert records[0]['requested_departments']==['고객지원부']
    assert records[0]['parser_failure_reason']=='부서·제목·지시 형식 오류'
    assert len(records[0]['output_sha256'])==64
    assert 'raw_output' not in records[0]
    assert 'prompt' not in records[0]


def test_corrupt_rejection_evidence_fails_closed(tmp_path):
    db=_db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute("UPDATE aiwack_wide_chief_rejected_attempts SET output_sha256='broken'")
    with pytest.raises(ValueError,match='손상'):
        read_failed_chief_plan_audit(db)
