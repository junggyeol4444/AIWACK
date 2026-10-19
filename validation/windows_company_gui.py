"""Second truly user-driven test: packaged Windows AIWACK.exe company and goal editing.

Only mouse/keyboard work in the GUI. SQLite is read-only used as an oracle.
Run from a GitHub Actions Windows desktop runner, on the test branch only.
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
import pyautogui
import pyperclip
import windows_built_exe_gui as gui

COMPANY="EXE Windows Test Company"
DESCRIPTION="Created by actual Windows screen interaction"
MISSION="Inspect save restart and durability"
GOAL="Plan created from Windows GUI"
DETAIL="Manual synthetic goal; no real customers"

def snapshot(label):
    gui.snapshot("company-"+label)

def pixels_white(w, y, xs):
    image=pyautogui.screenshot().convert("RGB")
    points=[(w.left+x,w.top+y) for x in xs]
    if any(px<0 or py<0 or px>=image.width or py>=image.height for px,py in points):
        return False
    return all(min(image.getpixel(pt))>215 for pt in points)

def white_bands(w, start, end, xs=(185,350,650,800), required=3):
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        screenshot=pyautogui.screenshot().convert("RGB")
        points=[w.left+x for x in xs]
        hits=[y for y in range(start,end)
              if all(0<=px<screenshot.width and 0<=w.top+y<screenshot.height
                     and min(screenshot.getpixel((px,w.top+y)))>215 for px in points)]
        spans=[]
        if hits:
            begin=prev=hits[0]
            for y in hits[1:]:
                if y>prev+1:
                    if prev-begin>=14:spans.append((begin+prev)//2)
                    begin=y
                prev=y
            if prev-begin>=14:spans.append((begin+prev)//2)
        if len(spans)>=required:
            return spans
        time.sleep(.65)
    snapshot("missing-input-bands")
    raise AssertionError("Expected visible company edit form, found fewer than %d input rows" % required)

def blue_button_y(w, x, first, last):
    im=pyautogui.screenshot().convert("RGB")
    hits=[]
    for y in range(first,last):
        px,py=w.left+x,w.top+y
        if 0<=px<im.width and 0<=py<im.height:
            r,g,b=im.getpixel((px,py))
            if 40<=r<=135 and 85<=g<=190 and b>170 and b>g+30:
                hits.append(y)
    if not hits:
        snapshot("missing-save-button")
        raise AssertionError("User-visible blue save/add button not found")
    return (hits[0]+hits[-1])//2

def go_company(w):
    # Select the fifth visible section using the REAL dropdown and keyboard.
    nav_y=gui.dashboard_nav_y(w)
    if nav_y is None:
        snapshot("company-navigation-not-visible")
        raise AssertionError("Real Windows company navigation is not visible")
    gui.click(w,220,nav_y)
    pyautogui.press("home")
    pyautogui.press("down",presses=4,interval=.09)
    pyautogui.press("enter")
    time.sleep(.9)
    fields=white_bands(w,295,480,xs=(700,780,860,930),required=3)
    snapshot("company-screen-visible")
    return fields[:3]

def exercise(exe):
    base=Path(tempfile.mkdtemp(prefix="aiwack-company-win-exe-"))
    d=base/"userdata"
    db=d/"aiwack.sqlite3"
    proc=None
    try:
        proc=gui.start(exe,d)
        w=gui.find_window()
        snapshot("first-launch")
        gui.type_text(w,175,320,gui.USER)
        gui.type_text(w,175,401,gui.PASS)
        gui.type_text(w,175,483,gui.PASS)
        gui.click(w,175,545)
        gui.expect_db(db,"SELECT username FROM owner_accounts WHERE id=1",gui.USER)
        gui.wait_dashboard(w)
        snapshot("dashboard-after-owner-create")
        fields=go_company(w)
        for y,value in zip(fields,(COMPANY,DESCRIPTION,MISSION)):
            gui.type_text(w,230,y,value)
        snapshot("company-profile-typed")
        gui.click(w,200,blue_button_y(w,200,fields[-1]+22,fields[-1]+115))
        gui.expect_db(db,"SELECT name FROM company_profile WHERE id=1",COMPANY)
        snapshot("company-profile-saved")

        goal_fields=white_bands(w,520,660,xs=(190,300,650,790),required=1)
        goal_y=goal_fields[0]
        gui.type_text(w,200,goal_y,GOAL)
        gui.type_text(w,700,goal_y,DETAIL)
        snapshot("goal-text-typed")
        gui.click(w,245,blue_button_y(w,245,goal_y+22,goal_y+110))
        gui.expect_db(db,"SELECT title FROM company_goals ORDER BY id DESC LIMIT 1",GOAL)
        snapshot("company-goal-saved")
        gui.shutdown(w,proc);proc=None
        snapshot("closed-after-company-save")

        proc=gui.start(exe,d)
        w=gui.find_window()
        snapshot("restarted-login")
        gui.type_text(w,175,395,gui.USER)
        gui.type_text(w,175,437,gui.PASS)
        gui.click(w,175,480)
        gui.wait_dashboard(w)
        fields=go_company(w)
        # An actual 2022 failure screenshot showed GitHub's host terminal
        # becoming foreground after the GUI had displayed the saved company.
        # Read the Tk field using physical focus+clipboard and independently
        # verify that the focused Win32 HWND remains AIWACK; never fake data.
        shown=""
        for attempt in range(3):
            gui.click(w,220,fields[0])
            gui.ensure_foreground(w)
            pyperclip.copy("sentinel")
            pyautogui.hotkey("ctrl","a")
            pyautogui.hotkey("ctrl","c")
            time.sleep(.4)
            foreground=gui.pygetwindow.getActiveWindow()
            if foreground is not None and foreground._hWnd == w._hWnd:
                shown=pyperclip.paste()
                if shown==COMPANY:
                    break
            snapshot("company-visible-clipboard-retry-"+str(attempt+1))
            time.sleep(.5)
        assert shown==COMPANY,"Company GUI field did not restore saved value: "+repr(shown)
        with sqlite3.connect(db) as con:
            assert con.execute("SELECT title,detail FROM company_goals").fetchall()==[(GOAL,DETAIL)]
        snapshot("company-and-goal-survived-restart")
        nav_y=gui.dashboard_nav_y(w)
        if nav_y is None:
            raise AssertionError("Cannot find native logout navigation")
        gui.click(w,960,nav_y if nav_y < 153 else nav_y+12)
        time.sleep(.6)
        snapshot("logged-out")
        gui.shutdown(w,proc);proc=None
        print("PACKAGED_WINDOWS_EXE_COMPANY_GOAL_REAL_USER_PASS",gui.STEPS,flush=True)
    finally:
        if proc is not None: gui.kill_tree(proc)
        for i in range(10):
            try: shutil.rmtree(base);break
            except (OSError,PermissionError):
                if i==9: print("WARNING: could not clean temporary test folder",base,flush=True)
                else:time.sleep(.5)

if __name__=="__main__":
    try:
        exe=Path(sys.argv[1]).resolve()
        assert exe.is_file() and exe.name.lower()=="aiwack.exe"
        exercise(exe)
    except Exception:
        import traceback
        (gui.ART/"company-error.txt").write_text(traceback.format_exc(),encoding="utf-8")
        try: snapshot("failure")
        except Exception: pass
        traceback.print_exc()
        raise SystemExit(1)
    finally:
        (gui.ART/"company-steps.json").write_text(json.dumps(gui.STEPS,ensure_ascii=False,indent=2),encoding="utf-8")
