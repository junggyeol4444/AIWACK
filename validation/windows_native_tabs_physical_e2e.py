"""Black-box 59 native tab navigation smoke in compiled Windows AIWACK.exe.

This physically interacts with the actual packaged GUI using PyAutoGUI and
takes 59 independent screenshots from a BRAND NEW owner account. It is NOT
59 feature-acceptance passes or a substitute for T01-T20 full business E2E.
No desktop imports, source Tk widget lookups or direct database writes.
"""
from __future__ import annotations
import hashlib
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
import windows_packaged_real_gguf_queue_e2e as gui

TOTAL_NATIVE_TABS=59
OUT=Path(os.environ.get("AIWACK_NATIVE_TABS_EVIDENCE","native-tabs-physical-windows"))
OUT.mkdir(parents=True,exist_ok=True)
gui.ART=OUT
USER="real_windows_all_tabs_owner"
PASSWORD="all-native-tabs-2026-password"

def run(exe):
    assert os.name=="nt" and exe.is_file() and exe.name.lower()=="aiwack.exe"
    base=Path(tempfile.mkdtemp(prefix="aiwack-59-tab-real-exe-"))
    gui.DATA=base/"data"
    gui.DB=gui.DATA/"aiwack.sqlite3"
    process=None
    logs=[]
    try:
        process=gui.gui.start(exe,gui.DATA)
        w=gui.gui.find_window()
        gui.write(w,175,320,USER)
        gui.write(w,175,401,PASSWORD)
        gui.write(w,175,483,PASSWORD)
        gui.click(w,175,545)
        gui.wait_sql("SELECT username FROM owner_accounts WHERE id=1",USER)
        gui.wait_office_dashboard(w)
        gui.evidence("real-exe-first-login-dashboard")
        for idx in range(TOTAL_NATIVE_TABS):
            if process.poll() is not None:
                raise AssertionError("Packaged EXE crashed while opening tab #%d"%idx)
            # The readonly navigation combobox is the native UI's exact tab
            # order. Pressing keys invokes ComboboxSelected, not a Tk callback.
            gui.click(w,300,146)
            pyautogui.press("home")
            if idx:
                pyautogui.press("down",presses=idx,interval=.007)
            pyautogui.press("enter")
            time.sleep(.32)
            frame=pyautogui.screenshot().convert("RGB")
            wleft,wtop=w.left,w.top
            roi=frame.crop((max(0,wleft+35),max(0,wtop+185),
                            min(frame.width,wleft+1005),min(frame.height,wtop+700)))
            digest=hashlib.sha256(roi.tobytes()).hexdigest()
            file="tab-%02d.png"%idx
            frame.save(OUT/file)
            logs.append({"index":idx,"screenshot":file,"pixels_sha256":digest})
            if idx%10==0:
                print("PACKAGED_WINDOWS_ACTUAL_NATIVE_TAB_SCREEN",
                      idx, "of", TOTAL_NATIVE_TABS, flush=True)
        distinct=len({x["pixels_sha256"] for x in logs})
        if distinct<45:
            raise AssertionError("Physical selection did not display 45 distinct native screens: "+str(distinct))
        gui.gui.shutdown(w,process)
        process=None
        process=gui.gui.start(exe,gui.DATA)
        w=gui.gui.find_window()
        gui.write(w,175,395,USER)
        gui.write(w,175,437,PASSWORD)
        gui.click(w,175,480)
        gui.wait_office_dashboard(w)
        gui.evidence("all-tabs-sweep-exe-reopened")
        gui.gui.shutdown(w,process)
        process=None
        print("PACKAGED_WINDOWS_59_NATIVE_TABS_PHYSICAL_NAVIGATION_PASS",
              "screens",len(logs),"distinct",distinct,flush=True)
    except Exception:
        (OUT/"failure.txt").write_text(traceback.format_exc(),encoding="utf-8")
        try:gui.evidence("native-tabs-physical-windows-failure")
        except Exception:pass
        raise
    finally:
        (OUT/"tab-digests.json").write_text(json.dumps(
            {"count":len(logs),"entries":logs,
             "only_tests":"visible native tab navigation and restart",
             "does_not_prove":"T01-T20 full business outcomes"},
            indent=2),encoding="utf-8")
        if process is not None:gui.gui.kill_tree(process)
        for _ in range(12):
            try:shutil.rmtree(base);break
            except OSError:time.sleep(.5)

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("usage: windows_native_tabs_physical_e2e.py AIWACK.exe")
    run(Path(sys.argv[1]).resolve())
