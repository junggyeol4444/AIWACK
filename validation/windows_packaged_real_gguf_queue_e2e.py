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


# The original pygetwindow object can become invalid after a Tk dialog changes.
# Keep the verified HWND, title and process identity; never click a guessed
# coordinate to restore foreground focus or use a stale HWND.
_WINDOW_IDENTITY = {}
_TARGET_EXE_PID = None


def _owner_pid(hwnd):
    actual = _native_window_pid(hwnd)
    if _TARGET_EXE_PID is not None and actual != _TARGET_EXE_PID:
        raise AssertionError("The visible GUI HWND does not belong to this AIWACK.exe process")
    return actual



def _win_pid(hwnd):
    import ctypes
    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
    return int(pid.value)


def _is_window(hwnd):
    import ctypes
    return bool(ctypes.windll.user32.IsWindow(int(hwnd)))


def _live_window(w):
    old_hwnd = int(w._hWnd)
    if _is_window(old_hwnd):
        name = w.title
        pid = _win_pid(old_hwnd)
        if not name or pid <= 0:
            raise AssertionError("Windows EXE HWND lacks verified process identity")
        known = _WINDOW_IDENTITY.get(old_hwnd)
        if known and known != (name, pid):
            raise AssertionError("Windows HWND reused by another process or title")
        _WINDOW_IDENTITY[old_hwnd] = (name, pid)
        return w
    old_identity = _WINDOW_IDENTITY.get(old_hwnd)
    if not old_identity:
        raise AssertionError("Stale Windows EXE HWND has no previous verified identity")
    name, pid = old_identity
    candidates = []
    for candidate in pygetwindow.getAllWindows():
        try:
            hwnd = int(candidate._hWnd)
            if (_is_window(hwnd) and candidate.title == name and
                    _win_pid(hwnd) == pid):
                candidates.append(candidate)
        except Exception:
            continue
    if len(candidates) != 1:
        raise AssertionError("Stale HWND cannot safely rebind to one live same-process window")
    recovered = candidates[0]
    _WINDOW_IDENTITY[int(recovered._hWnd)] = (name, pid)
    return recovered



# Preserve the identity of a destroyed Tk dialog across handle recreation.
WINDOW_TITLES={}
WINDOW_PIDS={}


def _native_window_pid(hwnd):
    if os.name!='nt':
        return None
    import ctypes
    api=ctypes.windll.user32
    api.IsWindow.argtypes=(ctypes.c_void_p,)
    api.IsWindow.restype=ctypes.c_bool
    api.GetWindowThreadProcessId.argtypes=(ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong))
    api.GetWindowThreadProcessId.restype=ctypes.c_ulong
    handle=ctypes.c_void_p(int(hwnd))
    if not api.IsWindow(handle):
        raise AssertionError('기존 창 HWND가 소멸했습니다.')
    pid=ctypes.c_ulong(0)
    if not api.GetWindowThreadProcessId(handle,ctypes.byref(pid)) or not pid.value:
        raise AssertionError('Tk 창의 실제 Windows PID를 확인할 수 없습니다.')
    return int(pid.value)


def _visible_window(w):
    """Reacquire a GUI window by exact title + original process, not guessed HWND."""
    hwnd=getattr(w,'_hWnd',None)
    try:
        title=w.title
        if title:WINDOW_TITLES[hwnd]=title
    except Exception:
        title=''
    name=WINDOW_TITLES.get(hwnd) or title
    if not name:raise AssertionError('Unknown native window; no physical click')
    pid=WINDOW_PIDS.get(name)
    if pid is None and hwnd is not None:
        try:
            pid=_native_window_pid(hwnd)
        except (AssertionError,OSError,ValueError):
            if os.name=='nt':
                raise AssertionError('Unknown original PID; physical click prohibited')
        if pid is not None:
            if _TARGET_EXE_PID is not None and pid != _TARGET_EXE_PID:
                raise AssertionError('Different Windows process owns the expected window')
            WINDOW_PIDS[name]=pid
    if os.name=='nt' and pid is None:
        raise AssertionError('Original Win32 process cannot be verified')
    for _ in range(5):
        try:windows=pygetwindow.getAllWindows()
        except Exception:windows=[]
        matched=[]
        for candidate in windows:
            try:
                if (candidate.title==name and candidate.width>300
                        and candidate.height>250):
                    candidate_pid=_native_window_pid(candidate._hWnd)
                    if (globals().get('_TARGET_EXE_PID') is not None
                            and candidate_pid != globals()['_TARGET_EXE_PID']):
                        raise AssertionError('The candidate HWND does not belong to the verified AIWACK process')
                    if pid is None or candidate_pid==pid:
                        matched.append(candidate)
            except Exception:
                continue
        if len(matched)==1:
            candidate=matched[0]
            try:
                candidate.left;candidate.top;candidate.width;candidate.height
                WINDOW_TITLES[candidate._hWnd]=name
                if pid is not None:WINDOW_PIDS[name]=pid
                return candidate
            except Exception:
                pass
        if len(matched)>1:
            evidence('native-window-missing-or-ambiguous')
            raise AssertionError('Expected one live native window %r, got %d'%(name,len(matched)))
        time.sleep(.12)
    evidence('native-window-missing-or-ambiguous')
    raise AssertionError('Expected one live native window %r, got 0'%(name,))


def _stable_native_rect(w):
    """Win32 1400 can invalidate a Tk property halfway through reading geometry."""
    for _ in range(4):
        try:
            live=_visible_window(w)
            rect=(live.left,live.top,live.width,live.height)
            if rect[2]>300 and rect[3]>250:
                return live,rect
        except (OSError,AssertionError,ValueError):
            pass
        time.sleep(.10)
    evidence('native-window-geometry-unstable')
    raise AssertionError('Native GUI geometry changed during verification')


def close_dialog_safely(w,expected_title):
    """Close only an exact Tk modal, never the main company owner dashboard."""
    if not isinstance(expected_title,str) or not expected_title.startswith('AIWACK |'):
        raise AssertionError('Expected a separate Windows window dialog')
    live=_visible_window(w)
    if live.title!=expected_title:
        raise AssertionError('Refusing close: different Windows window')
    candidates=[]
    for window in pygetwindow.getAllWindows():
        try:
            if window.title==expected_title:
                candidates.append(window)
        except Exception:
            pass
    if len(candidates)!=1 or int(candidates[0]._hWnd)!=int(live._hWnd):
        raise AssertionError('Refusing close: different Windows window or ambiguous modal')
    live.close()
    deadline=time.monotonic()+4
    original_hwnd=int(live._hWnd)
    while time.monotonic()<deadline:
        still_open=False
        for candidate in pygetwindow.getAllWindows():
            try:
                if (int(candidate._hWnd)==original_hwnd
                        and candidate.title==expected_title and _is_window(original_hwnd)):
                    still_open=True
                    break
            except Exception:
                continue
        if not still_open:
            return True
        time.sleep(.15)
    evidence('targeted-modal-close-timeout')
    raise AssertionError('Targeted Tk dialog did not close; no other window was touched')


def _active_is(w):
    try:
        active = pygetwindow.getActiveWindow()
        return active is not None and int(active._hWnd) == int(w._hWnd)
    except Exception:
        return False


def _focus_verified(w):
    w = _visible_window(_live_window(w))
    for _ in range(3):
        if _active_is(w):
            return _visible_window(_live_window(w))
        try:
            if w.isMinimized:
                w.restore()
            w.activate()
        except Exception:
            w = _visible_window(_live_window(w))
        time.sleep(.4)
        w = _visible_window(_live_window(w))
        if _active_is(w):
            return w
    raise AssertionError("Verified Windows GUI is not foreground: refused blind coordinate click")


def find_dialog(fragment, timeout=65):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = []
        try:
            windows = pygetwindow.getAllWindows()
        except (RuntimeError, OSError) as exc:
            # Win32 1400 indicates a destroyed Tk HWND: retry, never blind-click.
            if '1400' not in str(exc):
                raise
            time.sleep(.3)
            continue
        for win in windows:
            try:
                if (fragment in win.title and win.width >= 300
                        and _is_window(win._hWnd) and _owner_pid(win._hWnd)>0):
                    WINDOW_TITLES[int(win._hWnd)]=win.title
                    WINDOW_PIDS[win.title]=_owner_pid(win._hWnd)
                    found.append(_visible_window(_live_window(win)))
            except Exception:
                continue
        if len(found) == 1:
            return _focus_verified(found[0])
        if len(found) > 1:
            raise AssertionError("Ambiguous Windows dialogs: refuse unverified clicks")
        time.sleep(.3)
    evidence("dialog-not-found")
    raise AssertionError("Expected visible Windows GUI dialog not found: " + fragment)


def click(w, x, y):
    # Real Windows mouse only, guarded by valid HWND, process and foreground.
    w = _focus_verified(w)
    w, rect = _stable_native_rect(w)
    left, top, width, height = rect
    if width <= 500 or height <= 350:
        raise AssertionError("Packaged Windows EXE window has invalid dimensions")
    hwnd = int(w._hWnd)
    _owner_pid(hwnd)
    px, py = int(left + x), int(top + y)
    if x < 0 or y < 0 or x >= width or y >= height:
        raise AssertionError("Requested click is outside verified native window")
    # Never click after Tk has destroyed/recreated the dialog or focus changed.
    w = _visible_window(_live_window(w))
    if int(w._hWnd) != hwnd or not _active_is(w):
        raise AssertionError("Window identity changed before physical click")
    pyautogui.click(px, py)
    time.sleep(.6)



def _verify_native_keyboard_focus(w):
    """Require the exact live AIWACK.exe HWND before and after key commands."""
    current,_=_stable_native_rect(w)
    hwnd=int(current._hWnd)
    if _TARGET_EXE_PID is not None and _owner_pid(hwnd)!=_TARGET_EXE_PID:
        raise AssertionError('The selected Tk input is owned by another process')
    try:
        active=pygetwindow.getActiveWindow()
        if active is None or int(active._hWnd)!=hwnd:
            raise AssertionError('Windows foreground switched before keyboard input')
        if os.name=='nt':
            import ctypes
            win=ctypes.windll.user32
            win.GetForegroundWindow.restype=ctypes.c_void_p
            if not _is_window(hwnd) or int(win.GetForegroundWindow() or 0)!=hwnd:
                raise AssertionError('The intended native window disappeared before keyboard input')
    except AssertionError:
        raise
    except Exception as error:
        raise AssertionError('The native keyboard target cannot be verified') from error


def write(w, x, y, value):
    click(w, x, y)
    _verify_native_keyboard_focus(w)
    pyautogui.hotkey("ctrl", "a")
    _verify_native_keyboard_focus(w)
    pyautogui.write(value, interval=.008)


def write_task_title(w, title):
    """Find the visible white Tk work-entry by actual Windows pixels.

    Do not bypass GUI via SQLite INSERT, Tk callbacks or guessed stale y pixels.
    """
    shot = pyautogui.screenshot().convert("RGB")
    left, top = int(w.left), int(w.top)
    samples = (left + 240, left + 350, left + 460)
    if any(x < 0 or x >= shot.width for x in samples):
        raise AssertionError("Work entry sample outside actual Windows screenshot")
    segments = []
    start = None
    end = min(int(w.height) - 20, 675)
    for y in range(445, end):
        absolute = top + y
        if absolute < 0 or absolute >= shot.height:
            continue
        colors = [shot.getpixel((x, absolute)) for x in samples]
        bright = sum(min(rgb) >= 218 and max(rgb) - min(rgb) <= 32
                     for rgb in colors) >= 2
        if bright and start is None:
            start = y
        if not bright and start is not None:
            segments.append((start, y - 1))
            start = None
    if start is not None:
        segments.append((start, end - 1))
    candidates = [(a, b) for a, b in segments if 12 <= b - a + 1 <= 60]
    if len(candidates) != 1:
        evidence("actual-task-entry-pixel-not-unique")
        raise AssertionError("Expected exactly one actual white work-entry pixel region, got %r" % candidates)
    a, b = candidates[0]
    write(w, 240, (a + b) // 2, title)


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
    # Never send Alt+F4 to an unknown foreground process after Tk auto-close.
    _close_verified_dialog(dialog)
    time.sleep(.7)



def _close_verified_dialog(w):
    """Close the exact PID-verified Tk modal without ending the main EXE."""
    try:
        expected=WINDOW_TITLES.get(getattr(w,'_hWnd',None)) or w.title
        w=_focus_verified(_visible_window(w))
        return close_dialog_safely(w,expected)
    except AssertionError:
        return False


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
    global DATA, DB, _TARGET_EXE_PID
    assert os.name == "nt", "Actual Windows executable and desktop required"
    assert exe.is_file() and exe.name.lower() == "aiwack.exe"
    assert model_cli.is_file() and model_cli.name.lower() in {"llama-completion.exe", "llama-cli.exe"}
    assert gguf.is_file() and gguf.stat().st_size > 80000000
    with gguf.open("rb") as handle:
        assert handle.read(4) == b"GGUF", "A genuine GGUF binary must be connected"
    base = Path(tempfile.mkdtemp(prefix="aiwack-real-exe-company-"))
    DATA = base / "data"
    DB = DATA / "aiwack.sqlite3"
    p = None
    try:
        p = gui.start(exe, DATA)
        _TARGET_EXE_PID = p.pid
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
        write_task_title(w, TASK_TITLE)
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
        write_task_title(w, "Physical EXE second approved queue task")
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
            # Windows 2025 screenshot evidence: chief-order button y=610..641.
            click(w, 125, 626)
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
        # Windows 2025 screenshot evidence: approved queue y=610..641.
        click(w, 367, 626)
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
        # T17 partial: a hard Windows process termination AFTER genuine staff and
        # chief calls but BEFORE any owner review must not silently approve,
        # finalize, lose either artifact, or repeat the completed model calls.
        # Unlike the clean Alt+F4 restart below, this exercises forced EXE exit.
        evidence("t17-two-genuine-gguf-reviews-pending-before-hard-crash")
        gui.kill_tree(p)
        p.wait(timeout=20)
        p = None
        for current_id in (task_id, second_id):
            wait_sql("SELECT status FROM company_tasks WHERE id=?",
                     "in_progress", (current_id,))
            wait_sql("SELECT review_status FROM company_task_artifacts WHERE task_id=?",
                     "pending", (current_id,))
            current_artifact = read(
                "SELECT id FROM company_task_artifacts WHERE task_id=?", (current_id,))
            wait_sql("SELECT owner_decision FROM company_chief_task_reports WHERE artifact_id=?",
                     "pending", (current_artifact,))
        assert read("SELECT COUNT(*) FROM ai_model_call_history") == 6, (
            "Unexpected model call count after hard process termination")
        evidence("t17-hard-crash-persisted-both-unapproved-results")

        # Restart the SAME packaged EXE and data directory; use only the
        # visible mouse/keyboard login. The database is never repaired or
        # written by the driver. Owner approvals remain separate actions.
        p = gui.start(exe, DATA)
        w = gui.find_window()
        write(w, 175, 395, OWNER)
        write(w, 175, 437, PASSWORD)
        click(w, 175, 480)
        wait_office_dashboard(w)
        for current_id in (task_id, second_id):
            wait_sql("SELECT status FROM company_tasks WHERE id=?",
                     "in_progress", (current_id,))
            wait_sql("SELECT review_status FROM company_task_artifacts WHERE task_id=?",
                     "pending", (current_id,))
            current_artifact = read(
                "SELECT id FROM company_task_artifacts WHERE task_id=?", (current_id,))
            wait_sql("SELECT owner_decision FROM company_chief_task_reports WHERE artifact_id=?",
                     "pending", (current_artifact,))
        assert read("SELECT COUNT(*) FROM ai_model_call_history") == 6, (
            "The hard-crash restart must not silently rerun worker or chief")
        evidence("t17-hard-crash-reopened-exe-awaits-separate-owner-review")

        # Re-enter the existing RESULTS page through real physical GUI clicks.
        # The latest artifact occupies the first result row on this test fixture;
        # a wrong row is detected by the persisted per-artifact assertions below.
        click(w, 555, 270)
        click(w, 165, 483)
        click(w, 385, 572)
        # Queue UI originally opened the LAST pending report automatically.
        # After an abnormal exit, the owner must explicitly reopen it.
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
        # Failed Windows screenshot shows finalize button at y=565..598,
        # not at former y=625..657. Click the actual existing native GUI.
        click(w, 130, 572)
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
        click(w, 385, 572)
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
        click(w, 130, 572)
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
            _close_verified_dialog(result_window)
            time.sleep(.4)
            _close_verified_dialog(dialog)
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
        # x=532..608, y=610..642 (window-relative center 562,626).
        click(w, 562, 626)
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
        _close_verified_dialog(stopped_dialog)
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
