"""Black-box Windows EXE AI company first-screen E2E with physical mouse/keys.
No direct UI function calls. SQLite is queried READ-ONLY for postconditions.
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
import pyautogui
import windows_built_exe_gui as gui

NAME='Windows Office user-created business research work'


def snapshot(name):
    gui.snapshot('office-'+name)


def check_task(db):
    gui.expect_db(db,"SELECT title FROM company_tasks ORDER BY id DESC LIMIT 1",NAME,seconds=15)


def run(exe):
    base=Path(tempfile.mkdtemp(prefix='aiwack-office-e2e-'))
    directory=base/'data';db=directory/'aiwack.sqlite3'
    process=None
    try:
        process=gui.start(exe,directory)
        w=gui.find_window()
        snapshot('first-start-screen')
        gui.type_text(w,175,320,gui.USER)
        gui.type_text(w,175,401,gui.PASS)
        gui.type_text(w,175,483,gui.PASS)
        gui.click(w,175,545)
        gui.expect_db(db,"SELECT username FROM owner_accounts WHERE id=1",gui.USER)
        gui.wait_dashboard(w,seconds=100)
        snapshot('real-company-office-dashboard')
        # The default native Tk window is 1040x720. The company work editor
        # is visible at the lower-right, not an invisible widget API.
        gui.type_text(w,685,551,NAME)
        snapshot('work-typed-via-real-mouse')
        gui.click(w,930,553)
        check_task(db)
        snapshot('work-saved-from-real-screen')
        # Close the entire EXE, start an independent new process on same data.
        gui.shutdown(w,process);process=None
        process=gui.start(exe,directory)
        w=gui.find_window()
        gui.type_text(w,175,395,gui.USER)
        gui.type_text(w,175,437,gui.PASS)
        gui.click(w,175,480)
        gui.wait_dashboard(w,seconds=100)
        check_task(db)
        snapshot('restarted-office-with-persisted-work')
        gui.shutdown(w,process);process=None
        print('WINDOWS_OFFICE_PACKAGED_EXE_REAL_UI_PASS',NAME,flush=True)
    finally:
        if process is not None:gui.kill_tree(process)
        for i in range(10):
            try:shutil.rmtree(base);break
            except OSError:
                if i==9:print('WARNING: Windows temp database file locked',base,flush=True)
                else:time.sleep(.5)


if __name__=='__main__':
    try:
        exe=Path(sys.argv[1]).resolve()
        assert exe.name.lower()=='aiwack.exe' and exe.is_file()
        run(exe)
    except Exception:
        (gui.ART/'office-error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        try:snapshot('failure')
        except Exception:pass
        traceback.print_exc()
        sys.exit(1)
    finally:
        (gui.ART/'office-steps.json').write_text(json.dumps(gui.STEPS,indent=2,ensure_ascii=False),encoding='utf-8')
