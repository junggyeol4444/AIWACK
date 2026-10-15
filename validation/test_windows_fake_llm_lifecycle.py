"""Windows-native synthetic process lifecycle tests; this is NOT GGUF inference."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import threading
import time
import pytest
from desktop.model_runtime import ModelConfig, run_local_model

@pytest.fixture
def native_runner(tmp_path):
    configured = os.environ.get("AIWACK_NATIVE_SYNTHETIC_RUNNER", "")
    if configured:
        path = Path(configured).resolve()
        assert path.is_file() and path.suffix.lower() == ".exe"
        return path
    if os.name == "nt":
        pytest.fail("Windows runner must use an actual packaged synthetic .exe")
    path = tmp_path / "synthetic-native-runner"
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import os,sys,time\n"
        "if os.environ.get('AIWACK_SYNTHETIC_STALL_SECONDS') == '15': time.sleep(15)\n"
        "print('AIWACK_WINDOWS_NATIVE_CLI', ' '.join(sys.argv[1:])[:180])\n",
        encoding="utf-8")
    path.chmod(0o700)
    return path

def config(runner):
    return ModelConfig("SYNTHETIC cancellation regression", "llamafile", str(runner), "", 16)

def audit_spawn(monkeypatch):
    real_popen = subprocess.Popen
    children = []
    def wrapper(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        cmd = args[0] if args else kwargs.get("args", [])
        exe = str(cmd[0] if isinstance(cmd, (list, tuple)) and cmd else cmd)
        # A Windows taskkill helper is not another AI model invocation.
        if Path(exe).name.lower() not in ("taskkill", "taskkill.exe"):
            children.append(child)
        return child
    monkeypatch.setattr(subprocess, "Popen", wrapper)
    return children

def test_precancelled_request_never_launches_model(native_runner, monkeypatch):
    event = threading.Event()
    event.set()
    def forbidden(*args, **kwargs):
        pytest.fail("Pre-cancelled model request unexpectedly spawned")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    with pytest.raises(InterruptedError):
        run_local_model(config(native_runner), "실행 전 관리자 취소", cancel=event)

def test_windows_native_timeout_kills_child(native_runner, monkeypatch):
    monkeypatch.setenv("AIWACK_SYNTHETIC_STALL_SECONDS", "15")
    children = audit_spawn(monkeypatch)
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        run_local_model(config(native_runner), "timeout lifecycle", timeout=1)
    # The synthetic runner stalls for 15 seconds; a real cancellation must
    # terminate PyInstaller's process tree and release inherited pipes sooner.
    assert time.monotonic() - start < (10 if os.name == "nt" else 5.5)
    assert len(children) == 1 and children[0].poll() is not None

def test_inflight_owner_cancel_kills_child(native_runner, monkeypatch):
    monkeypatch.setenv("AIWACK_SYNTHETIC_STALL_SECONDS", "15")
    children = audit_spawn(monkeypatch)
    event = threading.Event()
    trigger = threading.Thread(target=lambda: (time.sleep(.45), event.set()), daemon=True)
    trigger.start()
    start = time.monotonic()
    with pytest.raises(InterruptedError):
        run_local_model(config(native_runner), "cancel lifecycle", timeout=8, cancel=event)
    trigger.join(timeout=2)
    # The synthetic runner stalls for 15 seconds; a real cancellation must
    # terminate PyInstaller's process tree and release inherited pipes sooner.
    assert time.monotonic() - start < (10 if os.name == "nt" else 5.5)
    assert len(children) == 1 and children[0].poll() is not None

def test_successful_relaunch_after_abort(native_runner, monkeypatch):
    monkeypatch.delenv("AIWACK_SYNTHETIC_STALL_SECONDS", raising=False)
    response = run_local_model(config(native_runner), "Korean prompt 한국어 테스트", timeout=20)
    assert response.startswith("AIWACK_WINDOWS_NATIVE_CLI")
    assert "Korean prompt 한국어 테스트" in response
