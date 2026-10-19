"""Stage 19: real SQLite model assignment and manually invoked offline call history."""
from pathlib import Path
import os
import sqlite3
import threading
import time

import pytest

from desktop.storage import AuthenticationError, LocalStore
from desktop.model_runtime import ModelConfig
from desktop.employee_model_runtime import invoke_employee_model


def setup(tmp_path):
    db = LocalStore(tmp_path / "db.sqlite3")
    db.setup_owner("owner_user", "this-is-a-long-passphrase-2026")
    employee = db.add_employee_draft("staff_001", "Local staff")
    script = tmp_path / "local-llm-runner"
    script.write_text('#!/usr/bin/env python3\nimport sys\nprint("RESPONSE_FOR_TEST: " + " ".join(sys.argv[1:]))\n', encoding="utf-8")
    script.chmod(0o700)
    if os.name == 'nt':
        script = Path(__import__('sys').executable)
    gguf = tmp_path / "weights.gguf"
    gguf.write_bytes(b"GGUF\x03\x00\x00\x00")
    model_id = db.add_local_model(ModelConfig("private-model", "llama_cpp", str(script), str(gguf), 9))
    return db, employee, model_id, script, gguf


def test_owner_assignment_is_persistent_and_has_no_automatic_invocation(tmp_path, monkeypatch):
    db, employee, model, script, gguf = setup(tmp_path)
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("model started on assignment")))
    assert db.read_employee_model(employee) is None
    db.set_employee_model(employee, model)
    assert db.read_employee_model(employee)["model_id"] == model
    assert db.list_employee_models()[0]["employee_name"] == "Local staff"
    assert db.list_employee_model_calls(employee) == []
    db.logout()
    db2 = LocalStore(db.path)
    with pytest.raises(AuthenticationError):
        db2.read_employee_model(employee)
    with pytest.raises(AuthenticationError):
        db2.set_employee_model(employee, None)
    with pytest.raises(AuthenticationError):
        db2.list_employee_model_calls()
    db2.login("owner_user", "this-is-a-long-passphrase-2026")
    assert db2.read_employee_model(employee)["model_name"] == "private-model"
    with pytest.raises(ValueError, match="배정"):
        db2.delete_local_model(model)
    db2.set_employee_model(employee, None)
    assert db2.read_employee_model(employee) is None
    db2.delete_local_model(model)
    assert script.exists() and gguf.exists()


def test_validation_default_deny_inactive_and_database_constraints(tmp_path):
    db, employee, model, _, _ = setup(tmp_path)
    for ident in [0, -1, True, 9999]:
        with pytest.raises(ValueError):
            db.set_employee_model(employee, ident)
    with pytest.raises(ValueError):
        db.set_employee_model(9999, model)
    with pytest.raises(ValueError):
        db.begin_employee_model_call(employee, "valid question")
    db.set_employee_model(employee, model)
    with pytest.raises(ValueError):
        db.begin_employee_model_call(employee, " ")
    with pytest.raises(ValueError):
        db.begin_employee_model_call(employee, "A" * 3001)
    assert db.list_employee_model_calls() == []
    db.set_employee_inactive(employee)
    assert db.read_employee_model(employee) is None
    with pytest.raises(ValueError):
        db.set_employee_model(employee, model)
    with pytest.raises(ValueError):
        db.begin_employee_model_call(employee, "should not execute")
    # Also protect against bypass by raw SQL.
    with pytest.raises(sqlite3.IntegrityError):
        with db._connect() as con:
            con.execute("INSERT INTO ai_employee_model_assignments(employee_id,model_id) VALUES (?,?)", (employee, model))
    db.restore_employee_draft(employee)
    assert db.read_employee_model(employee) is None, "Reactivation must NOT auto restore model authorization"


@pytest.mark.skipif(os.name == "nt", reason="Portable Linux fixture executable; Windows binary exercises DB records via --self-test")
def test_manual_real_local_process_saves_metadata_but_not_prompts_or_outputs(tmp_path):
    db, employee, model, _, _ = setup(tmp_path)
    db.set_employee_model(employee, model)
    prompt = "SECRET_SENTINEL_REQUEST_9FZ"
    response = invoke_employee_model(db, employee, prompt, timeout=5)
    assert "RESPONSE_FOR_TEST" in response and prompt in response
    log = db.list_employee_model_calls(employee)[0]
    assert log["status"] == "success"
    assert log["model_id"] == model and log["model_name"] == "private-model"
    assert log["prompt_chars"] == len(prompt)
    assert log["output_chars"] == len(response)
    assert log["completed_at"] is not None
    data = db.path.read_bytes()
    assert prompt.encode() not in data
    assert response.encode() not in data
    with pytest.raises(ValueError):
        db.finish_employee_model_call(log["id"], "success")
    db.set_employee_model(employee, None)
    assert len(db.list_employee_model_calls(employee)) == 1
    db.delete_local_model(model)
    assert db.list_employee_model_calls(employee)[0]["model_name"] == "private-model"


@pytest.mark.skipif(os.name == "nt", reason="Portable Linux fixture executable")
def test_failed_run_and_missing_model_files_logged(tmp_path):
    db, employee, model, script, gguf = setup(tmp_path)
    db.set_employee_model(employee, model)
    script.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(17)\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="17"):
        invoke_employee_model(db, employee, "failing run", timeout=5)
    log = db.list_employee_model_calls(employee)[0]
    assert log["status"] == "failure"
    assert log["error_kind"] == "RuntimeError"
    assert "17" not in log["error_kind"]
    gguf.unlink()
    with pytest.raises(ValueError):
        invoke_employee_model(db, employee, "missing local weights", timeout=5)
    logs = db.list_employee_model_calls(employee)
    assert [x["status"] for x in logs] == ["failure", "failure"]
    assert logs[0]["error_kind"] == "ValueError"


@pytest.mark.skipif(os.name == "nt", reason="Linux subprocess timeout test")
def test_timeout_and_explicit_cancel_both_have_terminal_audit(tmp_path):
    db, employee, model, script, gguf = setup(tmp_path)
    db.set_employee_model(employee, model)
    script.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(15)\n", encoding="utf-8")
    with pytest.raises(TimeoutError):
        invoke_employee_model(db, employee, "sleeping", timeout=1)
    signal = threading.Event()
    def stop():
        time.sleep(.25)
        signal.set()
    worker = threading.Thread(target=stop)
    worker.start()
    with pytest.raises(InterruptedError):
        invoke_employee_model(db, employee, "interrupt please", timeout=5, cancel=signal)
    worker.join(timeout=2)
    assert [x["status"] for x in db.list_employee_model_calls(employee)] == ["cancelled", "timeout"]
    assert all(x["completed_at"] for x in db.list_employee_model_calls(employee))


def test_history_limits_and_store_upgrade(tmp_path):
    db, employee, model, _, _ = setup(tmp_path)
    db.set_employee_model(employee, model)
    call_id, _ = db.begin_employee_model_call(employee, "hello")
    with pytest.raises(ValueError):
        db.finish_employee_model_call(call_id, "unknown")
    with pytest.raises(ValueError):
        db.finish_employee_model_call(call_id, "failure", error_kind="confidential stack trace")
    db.finish_employee_model_call(call_id, "failure", error_kind="RuntimeError", duration_ms=9)
    with pytest.raises(ValueError):
        db.list_employee_model_calls(limit=1000)
    with pytest.raises(ValueError):
        db.list_employee_model_calls(limit=True)
    assert LocalStore(db.path).health()["status"] == "ok"
    reopened=LocalStore(db.path)
    reopened.login("owner_user", "this-is-a-long-passphrase-2026")
    assert reopened.list_employee_model_calls(employee)[0]["duration_ms"] == 9
