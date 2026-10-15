"""Black-box GUI test: packaged AIWACK.exe, real Windows mouse and keyboard."""
import os, sys, time, json, sqlite3, subprocess, tempfile, traceback
from pathlib import Path
import pyautogui, pygetwindow, pyperclip

TITLE="AIWACK | AI Autonomous Company"
USER="windows_exe_user"
PASS="synthetic-only-2026-password"
NOTE="Saved through actual packaged AIWACK executable"
ART=Path(os.getenv("AIWACK_PACKAGED_GUI_ARTIFACTS","packaged-e2e"))
ART.mkdir(parents=True,exist_ok=True)
STEPS=[]
pyautogui.FAILSAFE=True
pyautogui.PAUSE=.2

def snapshot(name):
    STEPS.append(name)
    pyautogui.screenshot().save(ART/(f"{len(STEPS):02d}-{name}.png"))

def find_window(timeout=80):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        wins=[w for w in pygetwindow.getWindowsWithTitle(TITLE) if w.title==TITLE and w.width>=780]
        if wins:
            w=wins[0]
            if w.isMinimized:w.restore()
            try:w.activate()
            except Exception:pass
            time.sleep(.8)
            return w
        time.sleep(.5)
    raise AssertionError("Real packaged EXE window not shown")

def click(w,x,y):
    pyautogui.click(w.left+x,w.top+y)
    time.sleep(.35)

def type_text(w,x,y,s):
    click(w,x,y)
    pyautogui.hotkey("ctrl","a")
    pyautogui.write(s,.02)

def expect_db(db,sql,expected,seconds=25):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        if db.is_file():
            try:
                with sqlite3.connect(db,timeout=2) as c:
                    r=c.execute(sql).fetchone()
                    if r and r[0]==expected:return
            except sqlite3.OperationalError:pass
        time.sleep(.5)
    raise AssertionError("Expected GUI-induced database state: "+repr(expected))

def start(exe,directory):
    return subprocess.Popen([str(exe)],cwd=str(exe.parent),env={**os.environ,"AIWACK_DATA_DIR":str(directory)})

def shutdown(w,p):
    try:w.activate()
    except Exception:pass
    pyautogui.hotkey("alt","f4")
    try:p.wait(timeout=20)
    except subprocess.TimeoutExpired:
        p.terminate();p.wait(timeout=8)
        raise AssertionError("EXE did not exit on Alt+F4")

def open_notes(w):
    # New user-facing "다음 화면" button in the tested EXE candidate.
    # Drive it only through a real Windows mouse click.
    click(w,370,163)
    time.sleep(1)

def kill_tree(p):
    if p.poll() is None:
        subprocess.run(["taskkill","/T","/F","/PID",str(p.pid)],
          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
        try:p.wait(timeout=10)
        except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)

def test(exe):
    with tempfile.TemporaryDirectory(prefix="aiwack-packaged-e2e-") as t:
        d=Path(t)/"data";db=d/"aiwack.sqlite3"
        p=start(exe,d)
        try:
            w=find_window();snapshot("first-launch")
            type_text(w,175,320,USER);type_text(w,175,401,PASS);type_text(w,175,483,PASS)
            click(w,175,545)
            expect_db(db,"select username from owner_accounts where id=1",USER)
            snapshot("account-created")
            open_notes(w);snapshot("notes-selected")
            type_text(w,200,417,NOTE);click(w,130,482)
            expect_db(db,"select value from system_metadata where key='local_manual_test'",NOTE)
            snapshot("note-saved")
            shutdown(w,p);snapshot("exit-success")
        finally:
            kill_tree(p)
        p=start(exe,d)
        try:
            w=find_window();snapshot("reopen-login")
            type_text(w,175,395,USER);type_text(w,175,437,PASS);click(w,175,480)
            time.sleep(2)
            open_notes(w)
            pyperclip.copy("empty")
            click(w,200,417);pyautogui.hotkey("ctrl","a");pyautogui.hotkey("ctrl","c")
            time.sleep(1)
            assert pyperclip.paste()==NOTE, "GUI did not show persisted note: "+repr(pyperclip.paste())
            snapshot("reopen-note-visible")
            click(w,960,162);time.sleep(.8);snapshot("logout")
            shutdown(w,p)
        finally:
            kill_tree(p)

if __name__=="__main__":
    try:
        exe=Path(sys.argv[1]).resolve()
        assert exe.is_file() and exe.name.lower()=="aiwack.exe"
        test(exe)
        print("PACKAGED_WINDOWS_EXE_REAL_MOUSE_KEYBOARD_PASS",STEPS)
    except Exception:
        (ART/"failure.txt").write_text(traceback.format_exc(),encoding="utf-8")
        try:snapshot("failure")
        except Exception:pass
        traceback.print_exc()
        raise SystemExit(1)
    finally:
        (ART/"steps.json").write_text(json.dumps(STEPS,indent=2),encoding="utf-8")
