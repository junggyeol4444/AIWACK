"""Actual GGUF inference smoke via PHYSICAL Windows packaged AIWACK.exe GUI.

No desktop.* imports, synthetic runners, fake model calls, DB writes or
automatic approvals are used by this test. This tests model inference plumbing
and ONE employee call, not reasoning quality or autonomous company operation.
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
import windows_packaged_company_full_e2e as gui_test

ART = Path(os.environ.get("AIWACK_REAL_GGUF_EVIDENCE", "real-gguf-windows"))
ART.mkdir(parents=True, exist_ok=True)

def stage(s):
    pyautogui.screenshot().save(ART / (s + ".png"))
    print("REAL_PACKAGED_EXE_GGUF_STAGE", s, flush=True)

def run(app_exe:Path, model_cli:Path, gguf:Path):
    assert os.name == "nt" and app_exe.name.lower() == "aiwack.exe"
    assert app_exe.is_file() and model_cli.name.lower() == "llama-cli.exe"
    assert model_cli.is_file() and gguf.is_file() and gguf.stat().st_size > 80000000
    assert gguf.open("rb").read(4) == b"GGUF", "Real GGUF header required"
    root=Path(tempfile.mkdtemp(prefix="aiwack-real-gguf-exe-"))
    data=root/"data"
    db=data/"aiwack.sqlite3"
    gui_test.DB=db
    gui_test.DATA=data
    process=None
    try:
        process=gui_test.gui.start(app_exe,data)
        window=gui_test.gui.find_window()
        stage("01-packaged-aiwack-exe-launched")
        gui_test.write(window,175,320,"real_gguf_owner")
        gui_test.write(window,175,401,"real-gguf-owner-password-2026")
        gui_test.write(window,175,483,"real-gguf-owner-password-2026")
        gui_test.click(window,175,545)
        gui_test.wait_sql("SELECT username FROM owner_accounts WHERE id=1",
                          "real_gguf_owner")
        gui_test.wait_office_dashboard(window)
        stage("02-owner-logged-in-from-exe")
        gui_test.click(window,215,270)
        gui_test.click(window,343,414)
        gui_test.confirm()
        gui_test.wait_sql("SELECT COUNT(*) FROM ai_employee_profiles",31)
        stage("03-company-staff-created-via-exe")

        # Physical model wizard clicks. Employee #3 is the first staff model,
        # not the default chief. Backend stays 'llama_cpp' (actual GGUF path).
        gui_test.click(window,515,413)
        dialog=gui_test.find_dialog("AIWACK | 로컬 AI 모델 연결",timeout=40)
        gui_test.click(dialog,170,155)
        pyautogui.press("home")
        pyautogui.press("down", presses=2, interval=.13)
        pyautogui.press("enter")
        gui_test.write(dialog,190,204,"Real SmolLM2 135M GGUF CPU probe")
        gui_test.write(dialog,190,311,str(model_cli))
        gui_test.write(dialog,190,362,str(gguf))
        gui_test.write(dialog,190,408,"48")
        stage("04-real-gguf-executable-model-paths-entered")
        gui_test.click(dialog,110,460)
        gui_test.wait_sql("SELECT COUNT(*) FROM ai_employee_model_assignments WHERE employee_id=3",
                          1,timeout=30)
        stage("05-real-gguf-model-config-connected")

        # Press the visible "실제 모델 1회 호출 테스트" button. This goes
        # through AIWACK.exe's real employee_model_runtime and subprocess.
        # No synthetic output, monkeypatching or external probe CLI call.
        gui_test.click(dialog,343,460)
        stage("06-real-exe-model-probe-physically-clicked")
        gui_test.wait_sql(
            "SELECT status FROM ai_employee_model_calls WHERE employee_id=3 ORDER BY id DESC LIMIT 1",
            "success",timeout=130)
        gui_test.wait_sql(
            "SELECT COUNT(*) FROM ai_employee_model_calls WHERE employee_id=3",
            1,timeout=15)
        gui_test.wait_sql("SELECT COUNT(*) FROM company_task_artifacts",0)
        stage("07-genuine-gguf-inference-audited-success")
        gui_test.gui.shutdown(window,process)
        process=None

        # Reopen THE SAME installed Windows EXE and verify stored audit.
        process=gui_test.gui.start(app_exe,data)
        window=gui_test.gui.find_window()
        gui_test.write(window,175,395,"real_gguf_owner")
        gui_test.write(window,175,437,"real-gguf-owner-password-2026")
        gui_test.click(window,175,480)
        gui_test.wait_office_dashboard(window)
        gui_test.wait_sql(
            "SELECT status FROM ai_employee_model_calls WHERE employee_id=3 ORDER BY id DESC LIMIT 1",
            "success")
        stage("08-reopened-exe-real-gguf-inference-audit-preserved")
        gui_test.gui.shutdown(window,process)
        process=None
        print("PACKAGED_WINDOWS_EXE_REAL_GGUF_INFERENCE_PROBE_PASS",flush=True)
    except Exception:
        stage("99-actual-gguf-exe-failure")
        (ART/"failure.txt").write_text(traceback.format_exc(),encoding="utf-8")
        raise
    finally:
        (ART/"stages.json").write_text(json.dumps({
            "model_kind":"SmolLM2-135M-Instruct-Q4_K_M real GGUF",
            "inference_engine":"llama-cli Windows CPU, not synthetic",
            "does_not_prove":"model intelligence, multi-department autonomy or real sales"
        },indent=2),encoding="utf-8")
        if process is not None:
            gui_test.gui.kill_tree(process)
        for _ in range(8):
            try:
                shutil.rmtree(root)
                break
            except OSError:
                time.sleep(.4)

if __name__=="__main__":
    if len(sys.argv)!=4:
        raise SystemExit("Usage: real_GGUF_probe.py AIWACK.exe llama-cli.exe real.gguf")
    run(*(Path(x).resolve() for x in sys.argv[1:]))
