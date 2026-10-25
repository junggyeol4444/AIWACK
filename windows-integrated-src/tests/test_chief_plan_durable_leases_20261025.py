"""총괄 5그룹 실제 GGUF 모델 중복 호출 방지용 SQLite 잠금 계약.

테스트는 임시 SQLite와 로컬 모델 설정만 사용한다. 실제 GGUF 호출·Windows
GUI 클릭 또는 24시간 검증을 수행하지 않는다.
"""
import sys
import time

import pytest

from desktop import company_campaign_plan_leases as leases
from desktop import company_wide_campaign as wide
from desktop.company_operations import create_task, initialize_company_blueprint
from desktop.model_runtime import ModelConfig
from desktop.storage import LocalStore


@pytest.fixture
def prepared(tmp_path):
    db=LocalStore(tmp_path / "plan-lease.sqlite3")
    db.setup_owner("owner", "chief-plan-lease-test-password-2026")
    initialize_company_blueprint(db)
    model=db.add_local_model(ModelConfig(
        "plan-lease-contract", "llamafile", sys.executable, "", 32))
    for employee in db.list_employee_records():
        db.set_employee_model(employee["id"], model)
    source=create_task(db, "사내 안전한 검토 계획", "외부 거래 없이 내부 검토")
    return db,source


def test_second_windows_session_cannot_start_same_chief_plan(prepared,monkeypatch):
    db,source=prepared
    first=leases.reserve(db,source)
    assert len(first)==32
    try:
        rows=leases.snapshot(db)
        assert len(rows)==1 and rows[0]["source_task_id"]==source
        assert rows[0]["owner_process_inspection_required"] is True
        monkeypatch.setattr(wide,"invoke_employee_model",
                            lambda *_args,**_kwargs: pytest.fail(
                                "중복 실제 모델 호출은 수행되면 안 됩니다."))
        with pytest.raises(RuntimeError,match="다른 Windows 창"):
            wide.propose(db,source)
        leases.release(db,source,"0"*32)
        assert len(leases.snapshot(db))==1
    finally:
        leases.release(db,source,first)
    assert leases.snapshot(db)==[]


def test_stale_lease_requires_owner_and_records_immutable_recovery(prepared):
    db,source=prepared
    token=leases.reserve(db,source)
    with db._connect() as con:
        con.execute("""UPDATE aiwack_chief_plan_leases
            SET started_epoch=? WHERE source_task_id=?""",
            (int(time.time())-200,source))
    with pytest.raises(PermissionError,match="직접 확인"):
        leases.clear_after_owner_inspection(db,source)
    assert len(leases.snapshot(db))==1
    recovered=leases.clear_after_owner_inspection(
        db,source,owner_confirmed=True)
    assert recovered["lease_cleared"] is True
    assert recovered["model_reinvoked"] is False
    assert leases.snapshot(db)==[]
    history=leases.recovery_history(db)
    assert len(history)==1 and history[0]["owner_confirmed"] is True
    with db._connect() as con:
        with pytest.raises(Exception):
            con.execute("DELETE FROM aiwack_chief_plan_lease_recoveries")
    leases.release(db,source,token)
    assert len(leases.recovery_history(db))==1


def test_young_lease_cannot_be_manually_cleared(prepared):
    db,source=prepared
    token=leases.reserve(db,source)
    try:
        with pytest.raises(ValueError,match="3분"):
            leases.clear_after_owner_inspection(
                db,source,owner_confirmed=True)
        assert len(leases.snapshot(db))==1
    finally:
        leases.release(db,source,token)


def test_boolean_source_id_and_owner_confirmation_rejected(prepared):
    db,source=prepared
    with pytest.raises(ValueError,match="번호"):
        leases.reserve(db,True)
    token=leases.reserve(db,source)
    try:
        with pytest.raises(PermissionError):
            leases.clear_after_owner_inspection(
                db,source,owner_confirmed=1)
    finally:
        leases.release(db,source,token)
