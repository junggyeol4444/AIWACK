"""Physical Windows packaged AIWACK.exe planning GUI, from a fresh owner DB.

This is ONLY a partial T09 acceptance: goal -> local proposal -> owner
approval -> a real persisted TODO task. It does not execute products, sales,
payments, high-quality business output, or invent commercial results.
No desktop source imports, no direct GUI callbacks, and no writable SQL.
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
import windows_packaged_real_gguf_queue_e2e as real

GOAL = "Windows user physical planning acceptance goal"
OWNER = "windows_planning_owner"
PASSWORD = "planning-owner-password-2026"
ART = Path(os.environ.get("AIWACK_PLANNING_GUI_EVIDENCE", "physical-planning-gui"))
ART.mkdir(parents=True, exist_ok=True)
real.ART = ART

def wait_at_least(sql, minimum, timeout=30):
    until=time.monotonic()+timeout
    got=None
    while time.monotonic()<until:
        try:
            got=real.read(sql)
            if got is not None and got>=minimum:
                return got
        except sqlite3.OperationalError:
            pass
        time.sleep(.4)
    real.evidence("planning-wait-failed")
    raise AssertionError("Visible planning UI action did not persist: %s count=%s expected >=%s" %
                         (sql,got,minimum))

def run(exe):
    assert os.name=="nt", "This is a packaged Windows GUI test"
    assert exe.is_file() and exe.name.lower()=="aiwack.exe"
    base=Path(tempfile.mkdtemp(prefix="aiwack-physical-planning-"))
    real.DATA=base/"data"
    real.DB=real.DATA/"aiwack.sqlite3"
    p=None
    result={"test":"fresh Windows packaged GUI goal scan approve restart",
            "model":"no inference, rule-based drafting", "t09_scope":"partial",
            "passed":False, "not_verified":["business_launch","product_sales","payments"]}
    try:
        p=real.gui.start(exe,real.DATA)
        w=real.gui.find_window()
        real.evidence("planning-fresh-exe-started")
        real.write(w,175,320,OWNER)
        real.write(w,175,401,PASSWORD)
        real.write(w,175,483,PASSWORD)
        real.click(w,175,545)
        real.wait_sql("SELECT username FROM owner_accounts WHERE id=1",OWNER)
        real.wait_office_dashboard(w)
        real.evidence("planning-owner-created-physical-windows")
        real.click(w,326,270)
        real.evidence("planning-gui-view-visible")
        # Goal bar is the first row immediately below the four KPI tiles.
        real.write(w,265,414,GOAL)
        pyautogui.press("enter")
        real.wait_sql("SELECT status FROM company_goals WHERE title=?", "active", (GOAL,))
        real.evidence("planning-active-goal-saved-by-physical-gui")
        # A deterministic LOCAL rule scan does not execute an AI model.
        real.click(w,382,456)
        wait_at_least("SELECT COUNT(*) FROM company_task_proposals WHERE status='pending'",1)
        real.wait_sql("SELECT COUNT(*) FROM company_tasks",0)
        real.evidence("planning-proposals-pending-no-execution")
        proposal=real.read("SELECT id FROM company_task_proposals WHERE status='pending' ORDER BY id LIMIT 1")
        assert proposal is not None
        # First list row, then owner-only approval button (not auto-execution).
        real.click(w,164,528)
        real.evidence("planning-first-pending-proposal-selected")
        real.click(w,266,653)
        real.confirm()
        real.wait_sql("SELECT status FROM company_task_proposals WHERE id=?", "approved",(proposal,))
        task=real.read("SELECT approved_task_id FROM company_task_proposals WHERE id=?",(proposal,))
        assert isinstance(task,int) and task>0
        real.wait_sql("SELECT status FROM company_tasks WHERE id=?","todo",(task,))
        real.wait_sql("SELECT COUNT(*) FROM company_task_artifacts WHERE task_id=?",0,(task,))
        real.evidence("planning-owner-approved-task-not-autostarted")
        real.gui.shutdown(w,p)
        p=None
        real.evidence("planning-exe-closed")
        p=real.gui.start(exe,real.DATA)
        w=real.gui.find_window()
        real.write(w,175,395,OWNER)
        real.write(w,175,437,PASSWORD)
        real.click(w,175,480)
        real.wait_office_dashboard(w)
        real.wait_sql("SELECT status FROM company_task_proposals WHERE id=?","approved",(proposal,))
        real.wait_sql("SELECT status FROM company_tasks WHERE id=?","todo",(task,))
        real.evidence("planning-proposal-and-todo-reopened-persisted")
        real.gui.shutdown(w,p)
        p=None
        result.update(passed=True, approved_task_id=task)
        print("PHYSICAL_WINDOWS_EXE_OWNER_GOAL_PROPOSAL_APPROVAL_RESTART_PASS",flush=True)
    except Exception:
        (ART/"failure.txt").write_text(traceback.format_exc(),encoding="utf8")
        try:real.evidence("planning-physical-gui-failure")
        except Exception:pass
        raise
    finally:
        (ART/"result.json").write_text(json.dumps(result,indent=2),encoding="utf8")
        (ART/"steps.json").write_text(json.dumps(real.STEPS,indent=2),encoding="utf8")
        if p is not None: real.gui.kill_tree(p)
        for _ in range(12):
            try:shutil.rmtree(base);break
            except OSError:time.sleep(.5)

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("usage: windows_planning_physical_e2e.py AIWACK.exe")
    run(Path(sys.argv[1]).resolve())
