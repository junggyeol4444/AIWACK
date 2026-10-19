"""Windows PACKAGED AIWACK.exe actual-GGUF one-employee 60-minute stability test.

Real PyAutoGUI mouse and keyboard operate the packaged Windows GUI. No
desktop.* imports, Python model calls, DB mutations, fake model or callbacks.
Every employee response is inspected via a read-only SQLite model-call audit.
One-hour real GUI uptime and repeatedly initiated genuine inference IS NOT
proof of high-quality autonomous operations or T01-T20 full acceptance.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import traceback

import pyautogui
import windows_packaged_real_gguf_queue_e2e as real

MIN_DURATION_SECONDS = 60 * 60
EMPLOYEE_ID = 3
OWNER = "one_worker_windows_soak_owner"
PASSWORD = "soak-validation-local-password-2026"
OUT = Path(os.environ.get("AIWACK_LONG_SOAK_EVIDENCE", "aiwack-windows-soak"))
OUT.mkdir(parents=True, exist_ok=True)
real.ART = OUT


def audit_count():
    return real.read(
        "SELECT COUNT(*) FROM ai_model_call_history "
        "WHERE employee_id=? AND status='success'", (EMPLOYEE_ID,)) or 0


def model_probe(w, ordinal):
    # The real GUI, not desktop Python methods, triggers each genuine GGUF call.
    real.click(w, 215, 270)
    real.click(w, 515, 413)
    dialog = real.find_dialog("AIWACK | 로컬 AI 모델 연결", timeout=30)
    real.click(dialog, 170, 155)
    pyautogui.press("home")
    pyautogui.press("down", presses=EMPLOYEE_ID - 1, interval=.12)
    pyautogui.press("enter")
    before = audit_count()
    real.click(dialog, 325, 460)
    real.wait_sql(
        "SELECT COUNT(*) FROM ai_model_call_history "
        "WHERE employee_id=? AND status='success'",
        before + 1, (EMPLOYEE_ID,), timeout=95,
    )
    output_dialog = real.find_dialog(
        "AIWACK | 로컬 AI 직원 모델 호출 진단", timeout=25)
    if ordinal == 1 or ordinal % 10 == 0:
        real.evidence("one-worker-real-gguf-probe-%03d" % ordinal)
    try:
        output_dialog.activate()
    except Exception:
        pass
    pyautogui.hotkey("alt", "f4")
    time.sleep(.4)
    try:
        dialog.activate()
    except Exception:
        pass
    pyautogui.hotkey("alt", "f4")
    time.sleep(.4)


def run(exe, model_cli, gguf):
    assert os.name == "nt", "Run only on a real Windows desktop"
    assert exe.name.lower() == "aiwack.exe" and exe.is_file()
    assert model_cli.name.lower() == "llama-completion.exe" and model_cli.is_file()
    assert gguf.is_file() and gguf.stat().st_size > 80000000
    with gguf.open("rb") as model:
        assert model.read(4) == b"GGUF", "No genuine GGUF model"
    base = Path(tempfile.mkdtemp(prefix="aiwack-one-worker-60min-win-"))
    real.DATA = base / "data"
    real.DB = real.DATA / "aiwack.sqlite3"
    p = None
    results = {
        "test": "single_real_worker_60min_packaged_windows_mouse_keyboard",
        "kind": "genuine_gguf_not_synthetic",
        "requested_minimum_seconds": MIN_DURATION_SECONDS,
        "employee_id": EMPLOYEE_ID,
        "completed_calls": 0,
        "passed": False,
        "not_verified": [
            "autonomous_no_owner_input", "high_quality_business_output",
            "T01_to_T20_full_acceptance", "Windows11_personal_PC",
            "revenue_or_real_customer_transactions",
        ],
    }
    try:
        p = real.gui.start(exe, real.DATA)
        w = real.gui.find_window()
        real.evidence("real-packaged-exe-started")
        real.write(w, 175, 320, OWNER)
        real.write(w, 175, 401, PASSWORD)
        real.write(w, 175, 483, PASSWORD)
        real.click(w, 175, 545)
        real.wait_sql("SELECT username FROM owner_accounts WHERE id=1", OWNER)
        real.wait_office_dashboard(w)
        real.evidence("real-owner-created-and-logged-in")
        real.click(w, 215, 270)
        real.click(w, 343, 414)
        real.confirm()
        real.wait_sql("SELECT COUNT(*) FROM company_departments", 15)
        real.wait_sql("SELECT COUNT(*) FROM ai_employee_profiles", 31)
        real.bind_model(w, EMPLOYEE_ID-1, model_cli, gguf)
        real.wait_sql("SELECT COUNT(*) FROM ai_employee_model_assignments "
                      "WHERE employee_id=?", 1, (EMPLOYEE_ID,))
        real.evidence("real-worker-gguf-bound-through-gui")
        first = time.monotonic()
        elapsed = 0.0
        n = 0
        # An EXE left open and genuinely serving model requests for a FULL
        # hour; not a code-level loop invoking the Python model backend.
        while elapsed < MIN_DURATION_SECONDS:
            if p.poll() is not None:
                raise AssertionError("AIWACK.exe exited during real 60-minute soak")
            n += 1
            model_probe(w, n)
            if audit_count() != n:
                raise AssertionError("Saved real GGUF audit count differs")
            elapsed = time.monotonic() - first
            results.update(completed_calls=n, elapsed_seconds=round(elapsed, 1))
            # Periodic actual Windows GUI screenshot and transparent progress;
            # preserve evidence even if the next model call fails.
            if n == 1 or n % 10 == 0:
                (OUT / "soak-progress.json").write_text(
                    json.dumps(results, indent=2), encoding="utf-8")
                print("WIN_REAL_GGUF_ONE_EMPLOYEE_SOAK",
                      "successful_calls", n, "elapsed_seconds", round(elapsed, 1),
                      flush=True)
            # Keep EXE open. At least one fresh actual GUI model call per minute.
            if elapsed < MIN_DURATION_SECONDS:
                time.sleep(min(45.0, MIN_DURATION_SECONDS - elapsed))
        if time.monotonic() - first < MIN_DURATION_SECONDS:
            raise AssertionError("Insufficient actual wall-clock Windows GUI uptime")
        real.evidence("real-packaged-exe-one-worker-60min-with-live-calls")
        real.gui.shutdown(w, p)
        p = None
        real.evidence("real-exe-closed-after-one-hour")
        p = real.gui.start(exe, real.DATA)
        w = real.gui.find_window()
        real.write(w, 175, 395, OWNER)
        real.write(w, 175, 437, PASSWORD)
        real.click(w, 175, 480)
        real.wait_office_dashboard(w)
        real.wait_sql("SELECT COUNT(*) FROM ai_employee_model_assignments "
                      "WHERE employee_id=?", 1, (EMPLOYEE_ID,))
        real.wait_sql("SELECT COUNT(*) FROM ai_model_call_history "
                      "WHERE employee_id=? AND status='success'",
                      n, (EMPLOYEE_ID,))
        real.evidence("reopened-exe-genuine-one-worker-history-persisted")
        real.gui.shutdown(w, p)
        p = None
        results["passed"] = True
        print("PACKAGED_WINDOWS_EXE_REAL_ONE_WORKER_60MIN_SOAK_PASS",
              "call_count", n, flush=True)
    except Exception:
        results["exception_type"] = sys.exc_info()[0].__name__
        (OUT / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        try:
            real.evidence("actual-windows-60min-soak-failed")
        except Exception:
            pass
        raise
    finally:
        (OUT / "soak-result.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8")
        (OUT / "steps.json").write_text(
            json.dumps(real.STEPS, indent=2), encoding="utf-8")
        if p is not None:
            real.gui.kill_tree(p)
        for _ in range(12):
            try:
                shutil.rmtree(base)
                break
            except OSError:
                time.sleep(.5)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: windows_one_worker_real_gguf_soak_e2e.py "
            "AIWACK.exe llama-completion.exe REAL.gguf"
        )
    run(*(Path(s).resolve() for s in sys.argv[1:]))
