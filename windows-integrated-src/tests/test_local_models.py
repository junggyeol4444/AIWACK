"""Stage 18: LOCAL file model adapter profiles and actual subprocess contracts."""
from pathlib import Path
import os
import sqlite3
import sys

import pytest

from desktop.model_runtime import ModelConfig, run_local_model, validate_config
from desktop.storage import AuthenticationError, LocalStore


def owner(tmp_path):
    db = LocalStore(tmp_path / "local.sqlite3")
    db.setup_owner("local_owner", "private-long-passphrase-2026")
    return db


def sample_files(tmp_path):
    exe = tmp_path / "local-runner"
    exe.write_text("#!/usr/bin/env python3\nimport sys\nprint('LOCAL_RESPONSE | ' + ' | '.join(sys.argv[1:]))\n", encoding="utf-8")
    exe.chmod(0o700)
    if os.name == 'nt':
        exe = Path(sys.executable)
    gguf = tmp_path / "weights.gguf"
    gguf.write_bytes(b"GGUF\x03\x00\x00\x00")
    return exe, gguf


def make_config(exe, gguf, name="Korean local", backend="llama_cpp", tokens=12):
    return ModelConfig(name, backend, str(exe), str(gguf), tokens)


def test_registry_stores_multiple_local_backends_without_starting_processes(tmp_path, monkeypatch):
    db = owner(tmp_path)
    exe, gguf = sample_files(tmp_path)
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no process on CRUD")))
    alpha = db.add_local_model(make_config(exe, gguf, "main"))
    beta = db.add_local_model(ModelConfig("embedded", "llamafile", str(exe), "", 32))
    assert [m["backend"] for m in db.list_local_models()] == ["llama_cpp", "llamafile"]
    assert db.read_local_model(beta)["model_path"] == ""
    db.update_local_model(alpha, make_config(exe, gguf, "edited", tokens=23))
    assert db.read_local_model(alpha)["max_tokens"] == 23
    with pytest.raises(ValueError, match="사용 중"):
        db.update_local_model(alpha, make_config(exe, gguf, "embedded"))
    db.delete_local_model(beta)
    assert [m["name"] for m in db.list_local_models()] == ["edited"]
    assert exe.exists() and gguf.exists(), "Deleting a profile must not delete user model files"


def test_admin_only_and_restart(tmp_path):
    db = owner(tmp_path)
    exe, gguf = sample_files(tmp_path)
    model_id = db.add_local_model(make_config(exe, gguf))
    db.logout()
    with pytest.raises(AuthenticationError):
        db.list_local_models()
    with pytest.raises(AuthenticationError):
        db.read_local_model(model_id)
    with pytest.raises(AuthenticationError):
        db.add_local_model(make_config(exe, gguf))
    with pytest.raises(AuthenticationError):
        db.update_local_model(model_id, make_config(exe, gguf))
    with pytest.raises(AuthenticationError):
        db.delete_local_model(model_id)
    db2 = LocalStore(db.path)
    db2.login("local_owner", "private-long-passphrase-2026")
    assert db2.read_local_model(model_id)["name"] == "Korean local"


@pytest.mark.parametrize("bad", ["https://example.com/x", "//host/share/model.gguf", "\\\\host\\share\\model.gguf", "relative.gguf"])
def test_rejects_urls_unc_relative_paths(tmp_path, bad):
    exe, gguf = sample_files(tmp_path)
    with pytest.raises(ValueError):
        validate_config(ModelConfig("bad", "llama_cpp", str(exe), bad, 16))


def test_missing_files_and_corrupt_model_are_rejected(tmp_path):
    exe, gguf = sample_files(tmp_path)
    gguf.write_bytes(b"NOPE")
    with pytest.raises(ValueError, match="머리글"):
        validate_config(make_config(exe, gguf))
    gguf.unlink()
    with pytest.raises(ValueError, match="존재"):
        validate_config(make_config(exe, gguf))
    with pytest.raises(ValueError):
        validate_config(ModelConfig("missing", "llama_cpp", "/totally/missing/exe", "", 20))


@pytest.mark.parametrize("backend,tokens", [("unknown", 10), ("llama_cpp", 0), ("llama_cpp", 513), ("llama_cpp", True)])
def test_unknown_backends_and_token_limits(tmp_path, backend, tokens):
    exe, gguf = sample_files(tmp_path)
    with pytest.raises(ValueError):
        validate_config(make_config(exe, gguf, backend=backend, tokens=tokens))


def test_duplicate_and_invalid_config_do_not_change_existing_data(tmp_path):
    db = owner(tmp_path)
    exe, gguf = sample_files(tmp_path)
    first = db.add_local_model(make_config(exe, gguf, "first"))
    with pytest.raises(ValueError, match="사용 중"):
        db.add_local_model(make_config(exe, gguf, "FIRST"))
    with pytest.raises(ValueError):
        db.update_local_model(first, make_config(exe, gguf, "bad", tokens=9000))
    assert db.read_local_model(first)["name"] == "first"
    with pytest.raises(ValueError):
        db.delete_local_model(90001)
    assert gguf.exists()


@pytest.mark.skipif(os.name == "nt", reason="test uses a portable Linux executable script; Windows binary checked separately")
def test_actual_local_subprocess_receives_prompt_as_literal_argument(tmp_path):
    exe, gguf = sample_files(tmp_path)
    malicious_looking_prompt = "hello; echo should-not-execute"
    output = run_local_model(make_config(exe, gguf), malicious_looking_prompt, timeout=5)
    assert "LOCAL_RESPONSE" in output
    assert "-m" in output and str(gguf) in output
    assert "-p" in output and malicious_looking_prompt in output
    assert "-n | 12" in output
    assert not (tmp_path / "should-not-execute").exists()


@pytest.mark.skipif(os.name == "nt", reason="Linux subprocess timeout test")
def test_subprocess_failure_and_timeout(tmp_path):
    exe, gguf = sample_files(tmp_path)
    exe.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(13)\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="13"):
        run_local_model(make_config(exe, gguf), "hello", timeout=5)
    exe.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(10)\n", encoding="utf-8")
    with pytest.raises(TimeoutError):
        run_local_model(make_config(exe, gguf), "hello", timeout=1)


def test_invalid_prompt_no_spawn(tmp_path, monkeypatch):
    exe, gguf = sample_files(tmp_path)
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("spawned!")))
    with pytest.raises(ValueError, match="질문"):
        run_local_model(make_config(exe, gguf), "", timeout=10)
    with pytest.raises(ValueError, match="질문"):
        run_local_model(make_config(exe, gguf), "x" * 3001, timeout=10)


def test_old_user_metadata_survives_schema_upgrade(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE system_metadata(id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL, value TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        con.execute("INSERT INTO system_metadata(key,value) VALUES('local_manual_test','old-data')")
    db = LocalStore(path)
    db.setup_owner("local_owner", "private-long-passphrase-2026")
    assert db.read_note() == "old-data"
    assert db.list_local_models() == []

@pytest.mark.skipif(os.name == "nt", reason="Linux executable cancellation test")
def test_explicit_cancellation_terminates_local_process(tmp_path):
    """A running model process is killed on cancellation rather than left orphaned."""
    import threading
    import time
    exe, gguf = sample_files(tmp_path)
    exe.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n", encoding="utf-8")
    event = threading.Event()
    result = []

    def worker():
        try:
            run_local_model(make_config(exe, gguf), "hello", timeout=30, cancel=event)
        except InterruptedError:
            result.append("cancelled")

    task = threading.Thread(target=worker)
    task.start()
    time.sleep(.3)
    event.set()
    task.join(timeout=3)
    assert not task.is_alive()
    assert result == ["cancelled"]


def test_llama_completion_and_cli_force_one_shot_without_changing_other_executables(tmp_path, monkeypatch):
    """No external program executes. Assert actual Popen argv passed by runtime."""
    from desktop import model_runtime
    emitted = []
    class FakeProcess:
        returncode = 0
        def communicate(self, timeout=None):
            return b'SYNTHETIC ONE TURN MODEL OUTPUT', b''
    def record_process(args, **kwargs):
        emitted.append(list(args))
        assert kwargs['shell'] is False
        return FakeProcess()
    monkeypatch.setattr(model_runtime.subprocess, 'Popen', record_process)
    gguf = tmp_path/'synthetic.gguf'
    gguf.write_bytes(b'GGUF\x00\x00\x00\x00')
    for program, expected in (('llama-completion.exe', True),
                              ('llama-cli.exe', True),
                              ('custom-runner.exe', False)):
        exe=tmp_path/program
        exe.write_bytes(b'SYNTHETIC TEST EXECUTABLE; NOT A WORKING MODEL')
        text=run_local_model(ModelConfig(program, 'llama_cpp', str(exe),
                                         str(gguf), 8), 'single turn only',timeout=5)
        assert text=='SYNTHETIC ONE TURN MODEL OUTPUT'
        assert ('--single-turn' in emitted[-1]) is expected
        assert emitted[-1][-2:] == (['8','--single-turn'] if expected else ['-n','8'])


def test_rejects_empty_or_truncated_model_responses(tmp_path, monkeypatch):
    from desktop import model_runtime
    exe, gguf = sample_files(tmp_path)
    class FakeProcess:
        returncode = 0
        def __init__(self, body):
            self.body = body
        def communicate(self, timeout=None):
            return self.body, b''
    for body in (b'', b'   ', b'X' * (model_runtime.MAX_OUTPUT + 1)):
        monkeypatch.setattr(model_runtime.subprocess, 'Popen',
                            lambda *args, body=body, **kwargs: FakeProcess(body))
        with pytest.raises(ValueError, match='응답'):
            run_local_model(make_config(exe, gguf), 'bounded reply', timeout=5)
    monkeypatch.setattr(model_runtime.subprocess, 'Popen',
                        lambda *args, **kwargs: FakeProcess(b'Z' * model_runtime.MAX_OUTPUT))
    assert len(run_local_model(make_config(exe, gguf), 'bounded reply', timeout=5)) == model_runtime.MAX_OUTPUT


def test_windows_heap_corruption_fails_without_returning_or_retrying(tmp_path, monkeypatch):
    """Synthetic termination simulates Windows 0xC0000374; not real GGUF."""
    from desktop import model_runtime
    exe, gguf = sample_files(tmp_path)
    invocations = []
    class FailedProcess:
        returncode = 0xC0000374
        def communicate(self, timeout=None):
            return b'This output must not be accepted', b'windows runtime failure'
    def spawn(*args, **kwargs):
        invocations.append(args)
        return FailedProcess()
    monkeypatch.setattr(model_runtime.subprocess, 'Popen', spawn)
    with pytest.raises(RuntimeError, match='0xC0000374'):
        run_local_model(make_config(exe, gguf), 'read-only diagnostics', timeout=5)
    assert len(invocations) == 1

def test_cancel_during_final_subprocess_result_discards_reply(tmp_path, monkeypatch):
    """A finished process must not override a late owner cancellation."""
    import threading
    from desktop import model_runtime
    exe, gguf = sample_files(tmp_path)
    cancel = threading.Event()
    calls = []
    class FinishAndCancel:
        returncode = 0
        def communicate(self, timeout=None):
            cancel.set()
            return b'SYNTHETIC COMPLETED BUT CANCELLED', b''
    def fake_start(*args, **kwargs):
        calls.append(args)
        return FinishAndCancel()
    monkeypatch.setattr(model_runtime.subprocess, 'Popen', fake_start)
    with pytest.raises(InterruptedError, match='취소'):
        run_local_model(make_config(exe, gguf), 'cancel after output', timeout=5, cancel=cancel)
    assert len(calls) == 1
