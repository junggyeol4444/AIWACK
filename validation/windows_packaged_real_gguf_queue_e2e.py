"""Windows black-box packaged AIWACK.exe company lifecycle.

The test process never imports desktop.* and never writes an application table.
ALL setup/actions go through physical PyAutoGUI clicks/keys in AIWACK.exe.
SQLite is opened read-only as an independent persisted-state oracle.
The CEO and staff executables are the SAME verified genuine llama.cpp GGUF engine.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
from urllib.parse import quote

import pyautogui
import pygetwindow

import windows_built_exe_gui as gui

OWNER = "real_gguf_queue_owner"
PASSWORD = "real-gguf-queue-owner-password-2026"
TASK_TITLE = "Physical EXE chief staff owner E2E task"
OBJECTIVE = "Prepare a bounded offline market research report"
ART = Path(os.environ.get("AIWACK_REAL_GGUF_QUEUE_EVIDENCE", "real-gguf-company-queue-e2e"))
ART.mkdir(parents=True, exist_ok=True)
STEPS = []
DATA = None
DB = None
pyautogui.FAILSAFE = True
pyautogui.PAUSE = .18


def evidence(stage):
    STEPS.append(stage)
    pyautogui.screenshot().save(ART / ("%02d-%s.png" % (len(STEPS), stage)))
    print("PACKAGED_COMPANY_REAL_EXE_STAGE", stage, flush=True)


def read(sql, params=()):
    if not DB.is_file():
        return None
    # No writable SQLite connection is ever opened by this test driver.
    uri = "file:" + quote(str(DB.resolve()).replace("\\", "/"), safe="/:") + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=2) as con:
        row = con.execute(sql, params).fetchone()
        return row[0] if row else None


def snapshot_real_model_audit():
    """Read only genuine persisted model-call metadata, even after GUI failure.

    Prompt, model text, stderr, and owner credentials must not enter evidence.
    This is an independent SQLite read-only oracle, NEVER a test DB mutation.
    """
    if DB is None or not DB.is_file():
        return []
    uri = "file:" + quote(str(DB.resolve()).replace("\\", "/"), safe="/:") + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=3) as con:
        has_table = con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='ai_model_call_history'"
        ).fetchone()[0]
        if not has_table:
            return []
        fields = ("employee_id", "status", "model_name", "prompt_chars",
                  "output_chars", "duration_ms", "error_kind")
        rows = con.execute("SELECT " + ",".join(fields) +
                           " FROM ai_model_call_history ORDER BY id").fetchall()
    records = [dict(zip(fields, row)) for row in rows]
    (ART / "real-model-calls-readonly.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print("READONLY_REAL_GGUF_CALL_AUDIT", json.dumps(records, ensure_ascii=False),
          flush=True)
    return records


def verify_two_tasks_real_model_calls():
    """Require four genuine CEO calls and two real staff calls, not a stub pass."""
    records = snapshot_real_model_audit()
    chiefs = [x for x in records if x["employee_id"] == 1]
    workers = [x for x in records if x["employee_id"] in (3, 5)]
    if (len(records) != 6 or len(chiefs) != 4 or len(workers) != 2
            or {x["employee_id"] for x in workers} != {3, 5}
            or any(x["status"] != "success" or x["output_chars"] <= 0
                   for x in records)):
        raise AssertionError(
            "Six genuine successful CEO/staff model invocations required; "
            "see real-model-calls-readonly.json for metadata-only audit")
    evidence("six-real-gguf-model-calls-audited-without-db-writes")


def wait_sql(sql, expected, params=(), timeout=70):
    deadline = time.monotonic() + timeout
    observed = None
    while time.monotonic() < deadline:
        try:
            observed = read(sql, params)
            if observed == expected:
                return
        except sqlite3.OperationalError:
            pass
        time.sleep(.4)
    evidence("sql-verification-failed")
    raise AssertionError("Read-only DB assertion failed: expected %r observed %r for %s" %
                         (expected, observed, sql))


def find_dialog(fragment, timeout=65):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        windows = [w for w in pygetwindow.getAllWindows()
                   if fragment in w.title and w.width >= 300]
        if windows:
            w = windows[0]
            if w.isMinimized:
                w.restore()
            try:
                w.activate()
            except Exception:
                pass
            return w
        time.sleep(.3)
    evidence("dialog-not-found")
    raise AssertionError("Expected visible Windows GUI dialog not found: " + fragment)


def click(w, x, y):
    # Real Windows mouse input, never tkinter Button.invoke or direct callbacks.
    assert w.width > 500 and w.height > 350, (w.title, w.width, w.height)
    for _ in range(3):
        foreground = pygetwindow.getActiveWindow()
        if foreground is not None and foreground._hWnd == w._hWnd:
            break
        if w.isMinimized:
            w.restore()
        try:
            w.activate()
        except Exception:
            pass
        time.sleep(.4)
        foreground = pygetwindow.getActiveWindow()
        if foreground is not None and foreground._hWnd == w._hWnd:
            break
        pyautogui.click(w.left + 125, w.top + 18)
        time.sleep(.6)
    else:
        evidence("gui-foreground-not-restored")
        raise AssertionError("Packaged AIWACK.exe dialog is not foreground; refuse blind clicks")
    pyautogui.click(w.left + x, w.top + y)
    time.sleep(.6)


def write(w, x, y, value):
    click(w, x, y)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.write(value, interval=.008)


def confirm():
    # A separate actual human-facing Tk/Windows confirmation has focus.
    time.sleep(.5)
    pyautogui.press("enter")
    time.sleep(.6)


def bind_model(w, employee_index, model_cli, gguf):
    """Connect actual local GGUF via the packaged application's mouse-only wizard."""
    dialog = None
    for attempt in range(3):
        try:
            w.activate()
        except Exception:
            pass
        click(w, 515, 413)
        try:
            dialog = find_dialog("AIWACK | 로컬 AI 모델 연결", timeout=9)
            break
        except AssertionError:
            evidence("real-model-dialog-retry-%d" % (attempt + 1))
            time.sleep(1)
    if dialog is None:
        raise AssertionError("Packaged EXE did not open local model wizard")
    evidence("real-gguf-wizard-employee-%d" % (employee_index + 1))
    click(dialog, 170, 155)
    pyautogui.press("home")
    if employee_index:
        pyautogui.press("down", presses=employee_index, interval=.12)
    pyautogui.press("enter")
    write(dialog, 190, 204, "Real GGUF CPU employee %d" % (employee_index + 1))
    # The wizard's default backend is 'llama_cpp', which requires a real GGUF.
    # Never switch to the 'llamafile' synthetic fixture from prior E2E tests.
    write(dialog, 190, 311, str(model_cli))
    write(dialog, 190, 362, str(gguf))
    write(dialog, 190, 408, "48")
    evidence("real-gguf-executable-and-file-entered-%d" % (employee_index + 1))
    click(dialog, 110, 460)
    wait_sql("SELECT COUNT(*) FROM ai_employee_model_assignments WHERE employee_id=?",
             1, (employee_index + 1,), timeout=30)
    evidence("real-gguf-model-bound-%d" % (employee_index + 1))
    try:
        dialog.activate()
    except Exception:
        pass
    pyautogui.hotkey("alt", "f4")
    time.sleep(.7)


def wait_office_dashboard(window, timeout=80):
    """Observe the visible selected company-overview navigation button.

    Earlier wait_dashboard probed (200,163), which was a dark border even
    when AIWACK.exe showed the successful dashboard. Screenshot-backed check.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        img = pyautogui.screenshot().convert("RGB")
        # This is the upper solid-blue bar, away from the white Korean text.
        x, y = window.left + 93, window.top + 255
        if 0 <= x < img.width and 0 <= y < img.height:
            red, green, blue = img.getpixel((x, y))
            if 40 <= red <= 145 and 70 <= green <= 195 and blue >= 175 and blue > red + 55:
                print("REAL_EXE_COMPANY_DASHBOARD_PIXEL_VISIBLE", (x, y), (red,green,blue), flush=True)
                return
        time.sleep(.35)
    evidence("real-exe-dashboard-pixel-absent")
    raise AssertionError("Actual EXE company overview button never visibly selected")


def perform(exe, model_cli, gguf):
    global DATA, DB
    assert os.name == "nt", "Actual Windows executable and desktop required"
    assert exe.is_file() and exe.name.lower() == "aiwack.exe"
    assert model_cli.is_file() and model_cli.name.lower() == "llama-completion.exe"
    assert gguf.is_file() and gguf.stat().st_size > 80000000
    with gguf.open("rb") as handle:
        assert handle.read(4) == b"GGUF", "A genuine GGUF binary must be connected"
    base = Path(tempfile.mkdtemp(prefix="aiwack-real-exe-company-"))
    DATA = base / "data"
    DB = DATA / "aiwack.sqlite3"
    p = None
    try:
        p = gui.start(exe, DATA)
        w = gui.find_window()
        evidence("actual-aiwack-exe-launched")
        write(w, 175, 320, OWNER)
        write(w, 175, 401, PASSWORD)
        write(w, 175, 483, PASSWORD)
        click(w, 175, 545)
        wait_sql("SELECT username FROM owner_accounts WHERE id=1", OWNER)
        wait_office_dashboard(w)
        evidence("owner-created-through-exe")

        # Click the actual organization tab, then actual blueprint button.
        click(w, 215, 270)
        evidence("organization-before-setup")
        click(w, 343, 414)
        confirm()
        wait_sql("SELECT COUNT(*) FROM company_departments", 15)
        wait_sql("SELECT COUNT(*) FROM ai_employee_profiles", 31)
        evidence("blueprint-created-through-exe")

        # Chief #1 and two distinct staff profiles #3 and #5 (not head #4).
        bind_model(w, 0, model_cli, gguf)
        bind_model(w, 2, model_cli, gguf)
        bind_model(w, 4, model_cli, gguf)

        # Register/assign task using the visible task board, not SQL INSERTs.
        click(w, 424, 270)
        write(w, 240, 614, TASK_TITLE)
        pyautogui.press("enter")
        wait_sql("SELECT title FROM company_tasks ORDER BY id DESC LIMIT 1", TASK_TITLE)
        task_id = read("SELECT id FROM company_tasks ORDER BY id DESC LIMIT 1")
        evidence("task-registered-through-exe")
        click(w, 170, 483)
        click(w, 334, 413)
        wait_sql("SELECT employee_id FROM company_task_assignments WHERE task_id=?",
                 3, (task_id,))
        evidence("worker-assigned-through-exe")

        # A second actual task is entered through the same Windows GUI,
        # and receives a different staff model via workload-based routing.
        write(w, 240, 614, "Physical EXE second approved queue task")
        pyautogui.press("enter")
        wait_sql("SELECT title FROM company_tasks ORDER BY id DESC LIMIT 1",
                 "Physical EXE second approved queue task")
        second_id=read("SELECT id FROM company_tasks ORDER BY id DESC LIMIT 1")
        # Real Windows screenshot: task rows are oldest-first. The new
        # SECOND row is y=513, not the existing selected row y=483.
        click(w, 170, 513)
        click(w, 334, 413)
        # Assert the actual second staff member before model execution.
        wait_sql("SELECT employee_id FROM company_task_assignments WHERE task_id=?",
                 5, (second_id,))
        wait_sql("SELECT COUNT(*) FROM company_task_assignments a "
                 "JOIN ai_employee_model_assignments m ON m.employee_id=a.employee_id "
                 "WHERE a.task_id=?", 1, (second_id,))
        evidence("second-worker-and-task-assigned-via-exe")


        # Two separate CEO orders must first be approved by the owner, via
        # physically-clicked Windows dialogs. Neither has executed yet.
        for current_id,row_y in ((second_id,513),(task_id,483)):
            click(w, 170, row_y)
            click(w, 125, 653)
            prompt=find_dialog("총괄 AI → 직원 업무 지휘",timeout=20)
            pyautogui.write(OBJECTIVE, .01)
            pyautogui.press("enter")
            draft=find_dialog("총괄 AI 지시 초안",timeout=90)
            wait_sql("SELECT COUNT(*) FROM company_task_runs WHERE task_id=?",
                     0,(current_id,))
            click(draft,110,470)
            wait_sql("SELECT COUNT(*) FROM company_chief_task_orders WHERE task_id=?",
                     1,(current_id,))
        evidence("two-orders-owner-approved-no-worker-started")
        for current_id in (task_id,second_id):
            wait_sql("SELECT COUNT(*) FROM company_task_runs WHERE task_id=?",
                     0,(current_id,))
        # One visible batch-action click (plus the owner's confirmation).
        # The desktop app itself must execute TWO workers and TWO chief reviews,
        # with no additional clicks by the acceptance driver.
        # Windows screenshot: approved queue blue button occupies x=289..447.
        # x=462 would click '결과' instead of starting the approved task queue.
        click(w, 367, 653)
        evidence("owner-clicked-approved-two-task-queue")
        confirm()
        for current_id in (task_id,second_id):
            wait_sql("SELECT status FROM company_task_runs WHERE task_id=? ORDER BY id DESC LIMIT 1",
                     "success", (current_id,), timeout=150)
            wait_sql("SELECT review_status FROM company_task_artifacts WHERE task_id=?",
                     "pending",(current_id,))
            aid=read("SELECT id FROM company_task_artifacts WHERE task_id=?",(current_id,))
            wait_sql("SELECT owner_decision FROM company_chief_task_reports WHERE artifact_id=?",
                     "pending",(aid,),timeout=150)
            wait_sql("SELECT status FROM company_tasks WHERE id=?","in_progress",(current_id,))
        artifact_id=read("SELECT id FROM company_task_artifacts WHERE task_id=?",(task_id,))
        evidence("two-staff-two-chief-reviews-automatic-after-one-queue-click")
        verify_two_tasks_real_model_calls()
        # Queue UI opens the LAST pending report, so use its matching artifact.
        last_artifact_id=read("SELECT id FROM company_task_artifacts WHERE task_id=?",(second_id,))
        report=find_dialog("총괄 AI 회수 보고서",timeout=30)
        artifact_id=last_artifact_id
        task_id=second_id
        # Screenshot: report dialog top=155, blue owner-accept button
        # screen y=630..663. Relative y=491 clicks its center, not above it.
        click(report, 115, 491)
        evidence("owner-accepted-chief-report-button-clicked")
        confirm()
        evidence("owner-chief-report-confirmation-entered")
        wait_sql("SELECT owner_decision FROM company_chief_task_reports WHERE artifact_id=?",
                 "accepted", (artifact_id,))
        wait_sql("SELECT review_status FROM company_task_artifacts WHERE id=?",
                 "pending", (artifact_id,))
        wait_sql("SELECT status FROM company_tasks WHERE id=?",
                 "in_progress", (task_id,))
        evidence("chief-report-accepted-not-autoapproved")

        # Artifact approval is NOT task completion. Finalize requires another
        # explicit owner confirmation/click, which is independently audited.
        click(w, 555, 270)
        click(w, 165, 483)
        click(w, 381, 414)
        confirm()
        wait_sql("SELECT review_status FROM company_task_artifacts WHERE id=?",
                 "approved", (artifact_id,))
        wait_sql("SELECT status FROM company_tasks WHERE id=?",
                 "in_progress", (task_id,))
        evidence("owner-approved-artifact-still-in-progress")
        click(w, 165, 483)
        # Actual Windows screenshot: final owner-finish blue button occupies
        # screen y=625..657; win title top=9. Click inside, not on border.
        click(w, 130, 636)
        evidence("owner-finalize-task-button-physically-clicked")
        confirm()
        evidence("owner-finalize-task-confirmed")
        wait_sql("SELECT status FROM company_tasks WHERE id=?", "done", (task_id,))
        evidence("separate-owner-finalize-to-done")

        # First task: independent report acceptance, artifact approval, and finalization.
        # The review list displays most recently created artifacts first.
        first_task_id = read("SELECT id FROM company_tasks WHERE title=?", (TASK_TITLE,))
        first_artifact_id = read(
            "SELECT id FROM company_task_artifacts WHERE task_id=?", (first_task_id,))
        assert first_task_id is not None and first_artifact_id is not None
        wait_sql("SELECT owner_decision FROM company_chief_task_reports WHERE artifact_id=?",
                 "pending", (first_artifact_id,))
        wait_sql("SELECT review_status FROM company_task_artifacts WHERE id=?",
                 "pending", (first_artifact_id,))
        click(w, 165, 513)
        click(w, 421, 636)
        first_report = find_dialog("총괄 AI 회수 보고서", timeout=30)
        evidence("first-task-chief-report-opened-through-exe")
        click(first_report, 115, 491)
        confirm()
        wait_sql("SELECT owner_decision FROM company_chief_task_reports WHERE artifact_id=?",
                 "accepted", (first_artifact_id,))
        wait_sql("SELECT review_status FROM company_task_artifacts WHERE id=?",
                 "pending", (first_artifact_id,))
        wait_sql("SELECT status FROM company_tasks WHERE id=?",
                 "in_progress", (first_task_id,))
        evidence("first-task-report-accepted-not-autoapproved")
        click(w, 165, 513)
        click(w, 381, 414)
        confirm()
        wait_sql("SELECT review_status FROM company_task_artifacts WHERE id=?",
                 "approved", (first_artifact_id,))
        wait_sql("SELECT status FROM company_tasks WHERE id=?",
                 "in_progress", (first_task_id,))
        evidence("first-task-artifact-approved-not-autofinished")
        click(w, 165, 513)
        click(w, 130, 636)
        confirm()
        wait_sql("SELECT status FROM company_tasks WHERE id=?", "done", (first_task_id,))
        evidence("first-task-separate-owner-finalize-to-done")

        # Real process shutdown/restart, same SQLite data dir and GUI re-login.
        gui.shutdown(w, p)
        p = None
        evidence("exe-closed-cleanly")
        p = gui.start(exe, DATA)
        w = gui.find_window()
        write(w, 175, 395, OWNER)
        write(w, 175, 437, PASSWORD)
        click(w, 175, 480)
        wait_office_dashboard(w)
        click(w, 424, 270)
        wait_sql("SELECT status FROM company_tasks WHERE id=?", "done", (task_id,))
        wait_sql("SELECT owner_decision FROM company_chief_task_reports WHERE artifact_id=?",
                 "accepted", (artifact_id,))
        wait_sql("SELECT review_status FROM company_task_artifacts WHERE id=?",
                 "approved", (artifact_id,))
        wait_sql("SELECT status FROM company_tasks WHERE id=?", "done", (first_task_id,))
        wait_sql("SELECT owner_decision FROM company_chief_task_reports WHERE artifact_id=?",
                 "accepted", (first_artifact_id,))
        wait_sql("SELECT review_status FROM company_task_artifacts WHERE id=?",
                 "approved", (first_artifact_id,))
        evidence("reopened-exe-shows-both-separately-approved-tasks")

        # Windows GUI-only verification of ALL 31 draft employee model bindings.
        # Binding is not inference: independently invoke each actual GGUF runner
        # through the application's existing "실제 모델 1회 호출 테스트" button.
        click(w, 215, 270)
        for employee_index in range(31):
            if employee_index not in (0, 2, 4):
                bind_model(w, employee_index, model_cli, gguf)
        wait_sql("SELECT COUNT(DISTINCT employee_id) "
                 "FROM ai_employee_model_assignments", 31, timeout=90)
        evidence("31-real-gguf-model-assignments-through-windows-exe")

        for employee_index in range(31):
            employee_id = employee_index + 1
            before = read(
                "SELECT COUNT(*) FROM ai_model_call_history "
                "WHERE employee_id=? AND status='success'", (employee_id,)) or 0
            click(w, 515, 413)
            dialog = find_dialog("AIWACK | 로컬 AI 모델 연결", timeout=25)
            click(dialog, 170, 155)
            pyautogui.press("home")
            if employee_index:
                pyautogui.press("down", presses=employee_index, interval=.12)
            pyautogui.press("enter")
            # The genuine GGUF probe is a physical click, not a direct Python
            # call to the model backend or a fabricated DB audit record.
            click(dialog, 325, 460)
            wait_sql("SELECT COUNT(*) FROM ai_model_call_history "
                     "WHERE employee_id=? AND status='success'",
                     before + 1, (employee_id,), timeout=95)
            result_window = find_dialog(
                "AIWACK | 로컬 AI 직원 모델 호출 진단", timeout=25)
            evidence("employee-%02d-real-gguf-model-probe-success" % employee_id)
            try:
                result_window.activate()
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
        wait_sql("SELECT COUNT(DISTINCT employee_id) FROM ai_model_call_history "
                 "WHERE status='success'", 31, timeout=20)
        wait_sql("SELECT COUNT(*) FROM ai_model_call_history "
                 "WHERE status='success'", 37, timeout=20)
        snapshot_real_model_audit()
        evidence("all-31-staff-real-gguf-probes-audited-no-sales-or-approval")

        # T20 partial: the owner physically clicks emergency stop in the
        # packaged EXE. This confirms LOCAL AI execution blocking only;
        # the project explicitly does not yet block external services.
        click(w, 424, 270)
        # Windows 2025 screenshot: red "비상 정지" button is screen
        # x=532..608, y=639..670 (window-relative center 562,646).
        click(w, 562, 646)
        confirm()
        wait_sql("SELECT stopped FROM local_emergency_control WHERE id=1", 1)
        wait_sql("SELECT state FROM local_emergency_control_events ORDER BY id DESC LIMIT 1", 1)
        evidence("owner-physical-emergency-stop-active")

        # An owner clicking a model-probe button MUST NOT be able to bypass
        # the persisted emergency stop. Verify no 38th model call appears.
        click(w, 215, 270)
        click(w, 515, 413)
        stopped_dialog = find_dialog("AIWACK | 로컬 AI 모델 연결", timeout=25)
        click(stopped_dialog, 325, 460)
        time.sleep(8)
        if read("SELECT COUNT(*) FROM ai_model_call_history") != 37:
            evidence("emergency-stop-model-call-bypass")
            raise AssertionError("Emergency-stop did not prevent new local GGUF inference")
        evidence("owner-probe-blocked-no-new-model-call")
        try:
            stopped_dialog.activate()
        except Exception:
            pass
        pyautogui.hotkey("alt", "f4")
        time.sleep(.5)

        # T07 partial: data and the safety stop must persist through an
        # actual process exit and fresh packaged EXE login, not a GUI refresh.
        gui.shutdown(w, p)
        p = None
        evidence("all-models-and-emergency-stop-exe-closed")
        p = gui.start(exe, DATA)
        w = gui.find_window()
        write(w, 175, 395, OWNER)
        write(w, 175, 437, PASSWORD)
        click(w, 175, 480)
        wait_office_dashboard(w)
        wait_sql("SELECT COUNT(DISTINCT employee_id) FROM ai_employee_model_assignments", 31)
        wait_sql("SELECT COUNT(DISTINCT employee_id) FROM ai_model_call_history WHERE status='success'", 31)
        wait_sql("SELECT COUNT(*) FROM ai_model_call_history WHERE status='success'", 37)
        wait_sql("SELECT stopped FROM local_emergency_control WHERE id=1", 1)
        wait_sql("SELECT status FROM company_tasks WHERE id=?", "done", (task_id,))
        wait_sql("SELECT status FROM company_tasks WHERE id=?", "done", (first_task_id,))
        evidence("reopened-exe-31-model-audits-and-emergency-stop-persisted")

        gui.shutdown(w, p)
        p = None
        print("PACKAGED_WINDOWS_EXE_REAL_GGUF_TWO_TASK_QUEUE_PASS", flush=True)
        print("REAL_GGUF_WINDOWS_SERVER_E2E_NOT_WINDOWS11_OR_AUTONOMOUS_COMPANY", flush=True)
    except Exception:
        evidence("failure")
        # Snapshot the real GUI model-call status before the disposable test
        # profile is cleaned up. Diagnostics must never approve a result.
        try:
            snapshot_real_model_audit()
        except Exception as diagnostic_error:
            (ART / "audit-diagnostic-error.txt").write_text(
                type(diagnostic_error).__name__ + ": " + str(diagnostic_error),
                encoding="utf-8")
        (ART / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        (ART / "steps.json").write_text(json.dumps(STEPS, indent=2), encoding="utf-8")
        if p is not None:
            gui.kill_tree(p)
        for i in range(12):
            try:
                shutil.rmtree(base)
                break
            except (PermissionError, OSError):
                time.sleep(.5)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: python windows_packaged_real_gguf_queue_e2e.py AIWACK.exe llama-completion.exe real.gguf")
    perform(*(Path(x).resolve() for x in sys.argv[1:]))
