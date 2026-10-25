"""Windows AIWACK GUI 외부 감시 EXE. 관리자가 직접 실행할 때만 활성화.
정상 종료 시 중지, 비정상 종료 시 횟수 제한 재기동. 모델/결제 재실행 없음.
Windows 재부팅 자동 시작 및 24시간 연속 실행 검증은 별개다.
"""
from __future__ import annotations
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

MAX_CRASHES = 3
CRASH_WINDOW_SECONDS = 600
BACKOFF_SECONDS = (5, 15, 60)

def _record(kind, **fields):
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "AIWACK"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "native_supervisor.jsonl"
    item = {"utc":datetime.now(timezone.utc).isoformat(),"kind":kind,**fields}
    data = (json.dumps(item,ensure_ascii=False,sort_keys=True)+"\n").encode("utf-8")
    fd = os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    try:
        os.write(fd,data)
        os.fsync(fd)
    finally:
        os.close(fd)

def _mutex(target):
    kernel = ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    name = "Local\\AIWACKSupervisor_" + hashlib.sha256(
        str(target).casefold().encode("utf-8")).hexdigest()[:32]
    handle = kernel.CreateMutexW(None,False,name)
    if not handle:
        raise OSError("Windows 중복 감시 잠금 생성 실패")
    if ctypes.get_last_error()==183:
        kernel.CloseHandle(ctypes.c_void_p(handle))
        raise RuntimeError("동일한 AIWACK.exe를 감시하는 프로세스가 이미 있습니다.")
    return kernel,handle

def run(executable=None):
    if os.name!="nt":
        raise OSError("Windows 10/11 전용 감시 실행기입니다.")
    target = (Path(executable).resolve() if executable else
              Path(sys.executable).resolve().parent/"AIWACK.exe")
    if not target.is_file() or target.suffix.lower()!=".exe":
        raise FileNotFoundError("AIWACK.exe가 없습니다.")
    if target==Path(sys.executable).resolve():
        raise ValueError("감시 프로세스는 자기 자신을 재실행할 수 없습니다.")
    kernel,handle=_mutex(target)
    crashes=[]
    try:
        _record("supervisor_started",exe=str(target),owner_started=True)
        while True:
            child=subprocess.Popen([str(target)],cwd=str(target.parent),
                                   close_fds=True)
            _record("gui_launched",pid=child.pid)
            try:
                code=child.wait()
            except KeyboardInterrupt:
                _record("supervisor_stopped_by_owner",gui_pid=child.pid,
                        gui_left_running=child.poll() is None)
                return 0
            _record("gui_exited",pid=child.pid,exit_code=code)
            if code==0:
                _record("normal_gui_exit_supervisor_stopped")
                return 0
            now=time.monotonic()
            crashes=[t for t in crashes if now-t<CRASH_WINDOW_SECONDS]
            crashes.append(now)
            if len(crashes)>MAX_CRASHES:
                _record("restart_limit_reached",crashes_in_window=len(crashes),
                        no_model_or_payment_replay=True)
                return 70
            delay=BACKOFF_SECONDS[min(len(crashes)-1,len(BACKOFF_SECONDS)-1)]
            _record("gui_restart_scheduled",delay_seconds=delay,
                    model_or_payment_replay=False)
            time.sleep(delay)
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))

if __name__=="__main__":
    try:
        if len(sys.argv)>2:
            raise ValueError("사용법: AIWACKSupervisor.exe [AIWACK.exe 경로]")
        sys.exit(run(sys.argv[1] if len(sys.argv)==2 else None))
    except (OSError,ValueError,RuntimeError) as exc:
        print("AIWACK 감시 중단:",exc,file=sys.stderr)
        sys.exit(2)
