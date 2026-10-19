"""Stage 20: owner-only local chief responses, real CLI results and deny-by-default."""
from pathlib import Path
import os
import sqlite3
import threading
import time

import pytest

from desktop.chief_runtime import invoke_chief_model
from desktop.model_runtime import ModelConfig
from desktop.storage import AuthenticationError, LocalStore


def setup(tmp_path):
    store = LocalStore(tmp_path / "local.sqlite3")
    store.setup_owner("ceo_owner", "owner-very-safe-password-2026")
    ceo = store.add_employee_draft("chief001", "AI 총괄")
    other = store.add_employee_draft("member001", "AI 직원")
    script = tmp_path / "trusted-local-llm"
    script.write_text("#!/usr/bin/env python3\nimport sys\nprint('REAL_LOCAL_RESULT ' + ' '.join(sys.argv[1:]))\n", encoding="utf-8")
    script.chmod(0o700)
    if os.name == 'nt':
        script = Path(__import__('sys').executable)
    gguf = tmp_path / "tiny.gguf"
    gguf.write_bytes(b"GGUF\x03\x00\x00\x00")
    model = store.add_local_model(ModelConfig("manual local", "llama_cpp", str(script), str(gguf), 8))
    return store, ceo, other, model, script


def test_owner_only_chief_profile_and_default_deny(tmp_path):
    store, ceo, other, model, script = setup(tmp_path)
    assert store.read_chief_profile() is None
    with pytest.raises(ValueError, match="총괄 AI"):
        invoke_chief_model(store, "Hello")
    assert store.list_employee_model_calls() == []
    store.assign_reporting_line(ceo, "ceo")
    assert store.read_chief_profile()["model_id"] is None
    with pytest.raises(ValueError, match="배정"):
        invoke_chief_model(store, "Hello")
    store.set_employee_model(other, model)
    with pytest.raises(ValueError, match="총괄 AI"):
        store.begin_employee_model_call(other, "hello", required_tier="ceo")
    store.set_employee_model(ceo, model)
    profile = store.read_chief_profile()
    assert profile["employee_id"] == ceo and profile["model_name"] == "manual local"
    with pytest.raises(ValueError):
        store.begin_employee_model_call(ceo, "hello", required_tier="staff")
    store.logout()
    with pytest.raises(AuthenticationError):
        invoke_chief_model(store, "hello")
    with pytest.raises(AuthenticationError):
        store.read_chief_profile()
    assert LocalStore(store.path).health()["status"] == "ok"
    store.login("ceo_owner", "owner-very-safe-password-2026")
    assert store.read_chief_profile()["model_id"] == model


@pytest.mark.skipif(os.name == "nt", reason="Test binary is a POSIX executable; Windows checks SQL via --self-test")
def test_real_local_chief_response_is_displayable_and_privacy_safe(tmp_path):
    store, ceo, other, model, script = setup(tmp_path)
    store.assign_reporting_line(ceo, "ceo")
    store.set_employee_model(ceo, model)
    prompt = "PRIVATE_PROMPT_STAGE20_A7XZ"
    answer = invoke_chief_model(store, prompt, timeout=5)
    assert "REAL_LOCAL_RESULT" in answer and prompt in answer
    calls = store.list_employee_model_calls(ceo)
    assert len(calls) == 1 and calls[0]["status"] == "success"
    assert calls[0]["prompt_chars"] == len(prompt)
    raw = store.path.read_bytes()
    assert prompt.encode() not in raw
    assert answer.encode() not in raw
    store.logout()
    reopened = LocalStore(store.path)
    reopened.login("ceo_owner", "owner-very-safe-password-2026")
    assert len(reopened.list_employee_model_calls(ceo)) == 1
    assert reopened.read_chief_profile()["model_id"] == model


@pytest.mark.skipif(os.name == "nt", reason="POSIX CLI fixture")
def test_chief_role_revocation_prevents_future_execution(tmp_path):
    store, ceo, other, model, script = setup(tmp_path)
    store.assign_reporting_line(ceo, "ceo")
    store.set_employee_model(ceo, model)
    store.unassign_reporting_line(ceo)
    with pytest.raises(ValueError, match="총괄 AI"):
        invoke_chief_model(store, "should not run")
    assert store.list_employee_model_calls() == []
    store.assign_reporting_line(ceo, "ceo")
    store.set_employee_inactive(ceo)
    assert store.read_chief_profile()["lifecycle"] == "inactive"
    with pytest.raises(ValueError, match="활성 총괄 AI"):
        invoke_chief_model(store, "should not run")
    assert store.list_employee_model_calls() == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX CLI fixture")
def test_chief_failure_cancel_and_timeout_audited_without_text(tmp_path):
    store, ceo, other, model, script = setup(tmp_path)
    store.assign_reporting_line(ceo, "ceo")
    store.set_employee_model(ceo, model)
    script.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(17)\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        invoke_chief_model(store, "PRIVATE_FAILED_PROMPT", timeout=5)
    script.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(20)\n", encoding="utf-8")
    with pytest.raises(TimeoutError):
        invoke_chief_model(store, "PRIVATE_TIMEOUT_PROMPT", timeout=1)
    cancelled = threading.Event()
    worker = threading.Thread(target=lambda: (time.sleep(.25), cancelled.set()))
    worker.start()
    with pytest.raises(InterruptedError):
        invoke_chief_model(store, "PRIVATE_CANCEL_PROMPT", timeout=5, cancel=cancelled)
    worker.join(timeout=2)
    assert [x["status"] for x in store.list_employee_model_calls(ceo)] == ["cancelled", "timeout", "failure"]
    assert b"PRIVATE_FAILED_PROMPT" not in store.path.read_bytes()
    assert b"PRIVATE_TIMEOUT_PROMPT" not in store.path.read_bytes()
    assert b"PRIVATE_CANCEL_PROMPT" not in store.path.read_bytes()


def test_chief_prompt_validation_and_no_audit(tmp_path):
    store, ceo, other, model, script = setup(tmp_path)
    store.assign_reporting_line(ceo, "ceo")
    store.set_employee_model(ceo, model)
    for prompt in ("", " ", "x" * 3001):
        with pytest.raises(ValueError):
            invoke_chief_model(store, prompt, timeout=5)
    assert store.list_employee_model_calls() == []
