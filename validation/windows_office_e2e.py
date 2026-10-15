"""Black-box Windows EXE: actual mouse/keyboard company cockpit workflow.

No import of the application module; no model mocking; DB is read-only oracle.
A UI step only passes after checking the result produced by the EXE.
"""
from __future__ import annotations
import json
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

import pyautogui
import windows_built_exe_gui as gui

NAME = 'Windows real-user company operations task'


def snapshot(name):
    gui.snapshot('company-v3-'+name)


def wait_company_view(window, seconds=100):
    """Wait for a visible blue selected '회사 현황' navigation button."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        image = pyautogui.screenshot().convert('RGB')
        x, y = window.left + 88, window.top + 234
        if 0 <= x < image.width and 0 <= y < image.height:
            r, g, b = image.getpixel((x, y))
            if 40 <= r <= 130 and 80 <= g <= 200 and b >= 170 and b > r + 60:
                time.sleep(.75)
                print('PACKAGED_EXE_COMPANY_OVERVIEW_VISIBLE', (r, g, b), flush=True)
                return
        time.sleep(.5)
    snapshot('company-not-visible')
    raise AssertionError('Actual Windows packaged EXE company overview not visible')


def open_work(window):
    # Real user click on the visible '업무 실행' top navigation.
    gui.click(window, 309, 233)
    time.sleep(.8)
    snapshot('work-board-visible')


def run(exe):
    base = Path(tempfile.mkdtemp(prefix='aiwack-office-v3-e2e-'))
    directory = base / 'data'
    db = directory / 'aiwack.sqlite3'
    process = None
    try:
        process = gui.start(exe, directory)
        window = gui.find_window()
        snapshot('first-launch')
        gui.type_text(window, 175, 320, gui.USER)
        gui.type_text(window, 175, 401, gui.PASS)
        gui.type_text(window, 175, 483, gui.PASS)
        gui.click(window, 175, 545)
        gui.expect_db(db, 'SELECT username FROM owner_accounts WHERE id=1', gui.USER)
        wait_company_view(window)
        snapshot('company-dashboard-after-first-setup')
        open_work(window)
        gui.type_text(window, 320, 585, NAME)
        snapshot('task-entry-filled')
        gui.click(window, 936, 584)
        gui.expect_db(db, 'SELECT title FROM company_tasks ORDER BY id DESC LIMIT 1', NAME)
        snapshot('task-created-from-real-gui')
        # Real user opens org screen, then results/approval list.
        gui.click(window, 196, 233)
        snapshot('real-organization-screen')
        gui.click(window, 442, 233)
        snapshot('results-approval-screen')
        gui.shutdown(window, process)
        process = None
        snapshot('packaged-exe-closed')
        process = gui.start(exe, directory)
        window = gui.find_window()
        snapshot('fresh-exe-login')
        gui.type_text(window, 175, 395, gui.USER)
        gui.type_text(window, 175, 437, gui.PASS)
        gui.click(window, 175, 480)
        wait_company_view(window)
        open_work(window)
        gui.expect_db(db, 'SELECT title FROM company_tasks ORDER BY id DESC LIMIT 1', NAME)
        snapshot('reopened-company-task-still-visible')
        gui.shutdown(window, process)
        process = None
        print('PACKAGED_WINDOWS_COMPANY_COCKPIT_MOUSE_KEYBOARD_PASS', NAME, flush=True)
    finally:
        if process is not None:
            gui.kill_tree(process)
        for i in range(12):
            try:
                shutil.rmtree(base)
                break
            except OSError:
                if i == 11:
                    print('WARNING temporary data folder still locked', base, flush=True)
                else:
                    time.sleep(.5)


if __name__ == '__main__':
    try:
        executable = Path(sys.argv[1]).resolve()
        assert executable.is_file() and executable.name.lower() == 'aiwack.exe'
        run(executable)
    except Exception:
        (gui.ART / 'company-v3-error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        try:
            snapshot('failure')
        except Exception:
            pass
        traceback.print_exc()
        sys.exit(1)
    finally:
        (gui.ART / 'company-v3-steps.json').write_text(json.dumps(gui.STEPS, indent=2, ensure_ascii=False), encoding='utf-8')
