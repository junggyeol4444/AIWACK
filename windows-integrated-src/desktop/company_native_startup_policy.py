"""Windows 로그인 시 외부 AIWACK 감시 EXE 실행 정책.

현재 사용자 HKCU Run만 명시적 관리자 GUI 클릭으로 설정한다.
로그인 전 자동 실행/Windows 서비스/24시간 무중단 보장은 하지 않는다.
기존 값 덮어쓰기·다른 프로그램/계정 설정 변경은 금지한다.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE = "AIWACKSupervisor"


def _require_windows():
    if os.name != "nt":
        raise OSError("Windows 10/11 네이티브 EXE에서만 설정할 수 있습니다.")


def _command():
    _require_windows()
    if not getattr(sys, "frozen", False):
        raise RuntimeError("실제 AIWACK.exe에서만 로그인 시작을 설정합니다.")
    app = Path(sys.executable).resolve(strict=True)
    if app.name.casefold() != "aiwack.exe":
        raise ValueError("기존 AIWACK.exe 실행 파일이 아닙니다.")
    supervisor = app.parent / "AIWACKSupervisor.exe"
    if not supervisor.is_file() or supervisor.is_symlink():
        raise FileNotFoundError("동일 폴더에 정식 AIWACKSupervisor.exe가 없습니다.")
    supervisor = supervisor.resolve(strict=True)
    if supervisor.parent != app.parent or supervisor.name.casefold()!="aiwacksupervisor.exe":
        raise ValueError("다른 경로의 감시 실행기는 등록할 수 없습니다.")
    return subprocess.list2cmdline([str(supervisor),str(app)])


def _read():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,_RUN_KEY,0,
                            winreg.KEY_READ) as key:
            return str(winreg.QueryValueEx(key,_VALUE)[0])
    except FileNotFoundError:
        return None


def status(store):
    store.require_permission("company:manage")
    if os.name != "nt":
        return {"windows_supported":False,"registered":False,
                "requires_user_logon":True,"continuous_24h_verified":False}
    current = _read()
    try:
        expected = _command()
        path_ready = True
        error = ""
    except (OSError,ValueError,RuntimeError) as exc:
        expected = None
        path_ready = False
        error = str(exc)
    return {"windows_supported":True,"packaged_paths_ready":path_ready,
            "path_error":error,"registered":current is not None,
            "matches_current_installation":bool(expected and current==expected),
            "existing_value_is_different":bool(current and current!=expected),
            "current_user_only":True,"requires_user_logon":True,
            "supervisor_launches_gui_not_models":True,
            "continuous_24h_verified":False,
            "registration_does_not_authenticate_owner":True}


def enable(store):
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    expected = _command()
    from desktop.company_native_supervisor import _record
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,_RUN_KEY,0,
                            winreg.KEY_READ|winreg.KEY_SET_VALUE) as key:
        try:
            existing = str(winreg.QueryValueEx(key,_VALUE)[0])
        except FileNotFoundError:
            existing = None
        if existing is not None and existing!=expected:
            raise PermissionError("기존 로그인 시작 항목이 달라 덮어쓰지 않습니다.")
        if existing==expected:
            return {"registered":True,"already_present":True,
                    "requires_user_logon":True,"continuous_24h_verified":False}
        _record("owner_startup_registration_requested",scope="HKCU Run",
                automatic_model_or_payment_execution=False)
        winreg.SetValueEx(key,_VALUE,0,winreg.REG_SZ,expected)
    _record("owner_startup_registered",scope="HKCU Run",
            automatic_model_or_payment_execution=False)
    return {"registered":True,"already_present":False,
            "requires_user_logon":True,"continuous_24h_verified":False,
            "owner_login_required":True}


def disable(store):
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    expected = _command()
    from desktop.company_native_supervisor import _record
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,_RUN_KEY,0,
                        winreg.KEY_READ|winreg.KEY_SET_VALUE) as key:
        try:
            existing = str(winreg.QueryValueEx(key,_VALUE)[0])
        except FileNotFoundError:
            return {"registered":False,"already_absent":True}
        if existing != expected:
            raise PermissionError("등록된 항목이 현재 실행 파일과 달라 삭제하지 않습니다.")
        _record("owner_startup_disable_requested",scope="HKCU Run")
        winreg.DeleteValue(key,_VALUE)
    _record("owner_startup_disabled",scope="HKCU Run")
    return {"registered":False,"already_absent":False,
            "existing_supervisor_process_not_terminated":True}
