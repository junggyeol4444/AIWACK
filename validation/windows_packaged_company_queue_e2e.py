"""Windows black-box packaged AIWACK.exe company lifecycle.

The test process never imports desktop.* and never writes an application table.
ALL setup/actions go through physical PyAutoGUI clicks/keys in AIWACK.exe.
SQLite is opened read-only as an independent persisted-state oracle.
The employee executable is a separately packaged SYNTHETIC fixture, not GGUF.
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

OWNER = "packaged_company_owner"
PASSWORD = "owner-packaged-e2e-password-2026"
TASK_TITLE = "Physical EXE chief staff owner E2E task"
OBJECTIVE = "Prepare a bounded offline market research report"
ART = Path(os.environ.get("AIWACK_PACKAGED_GUI_ARTIFACTS", "packaged-company-autocycle-e2e"))
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
    # Real Windows mouse input. Never invoke an application callback directly.
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


def bind_model(w, employee_index, exe):
    # The organization's public "로컬 모델 연결" dialog. No DB injection.
    # GUI-only recovery: clicking a model settings button has no database or
    # model-execution side effect. Windows 2025 occasionally misses the first
    # click after organization redraw. Wait for a REAL dialog; retry at most 3
    # times without injecting state or attempting any model registration twice.
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
            evidence("model-dialog-open-click-retry-%d" % (attempt + 1))
            time.sleep(1)
    if dialog is None:
        raise AssertionError("The real packaged EXE did not open its model connection dialog")
    evidence("local-model-dialog-employee-%s" % employee_index)
    click(dialog, 170, 155)
    pyautogui.press("home")
    if employee_index:
        pyautogui.press("down", presses=employee_index, interval=.12)
    pyautogui.press("enter")
    # The app correctly rejects duplicate registered model display names.
    # Set distinct labels via the ACTUAL editable GUI field; no SQL mutation.
    write(dialog, 190, 204, "AIWACK Native Synthetic Model " + str(employee_index))
    # Backends are llama_cpp, llamafile. Native synthetic CLI is a llamafile
    # adapter fixture; nothing here constitutes actual GGUF model inference.
    # Actual Windows screenshot showed llama_cpp still selected after merely
    # focusing the field and pressing End. Open the readonly combobox popup
    # through its right-side arrow, then choose the 2nd supported backend.
    click(dialog, 739, 258)
    pyautogui.press("home")
    pyautogui.press("down")
    pyautogui.press("enter")
    evidence("llamafile-backend-selected-employee-%s" % employee_index)
    write(dialog, 190, 311, str(exe))
    evidence("model-backend-and-executable-typed-employee-%s" % employee_index)
    click(dialog, 110, 460)
    evidence("model-connect-save-clicked-employee-%s" % employee_index)
    employee_id = employee_index + 1
    wait_sql("SELECT COUNT(*) FROM ai_employee_model_assignments WHERE employee_id=?",
             1, (employee_id,))
    evidence("model-path-bound-employee-%s" % employee_id)
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


def perform(exe, stub):
    global DATA, DB
    assert os.name == "nt", "Actual Windows executable and desktop required"
    assert exe.is_file() and exe.name.lower() == "aiwack.exe"
    assert stub.is_file() and stub.suffix.lower() == ".exe"
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

        # Chief #1 and first employee with 'staff' reporting tier #3.
        bind_model(w, 0, stub)
        bind_model(w, 2, stub)
        bind_model(w, 3, stub)

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
        # E2E must assert a real bound model rather than a hard-coded staff
        # ID: several valid ready employees may be chosen by office routing.
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

        # The first task still requires three distinct owner actions.
        # The read-only DB oracle verifies no automatic approval or completion.
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
        gui.shutdown(w, p)
        p = None
        print("PACKAGED_WINDOWS_EXE_APPROVED_TWO_TASK_QUEUE_PASS", flush=True)
        print("SYNTHETIC_APPROVED_TWO_TASK_QUEUE_NOT_GGUF_NOT_WINDOWS11", flush=True)
    except Exception:
        evidence("failure")
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
    if len(sys.argv) != 3:
        raise SystemExit("usage: python windows_packaged_company_full_e2e.py AIWACK.exe ModelStub.exe")
    perform(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
