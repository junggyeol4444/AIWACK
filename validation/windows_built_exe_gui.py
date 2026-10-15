"""Black-box GUI test: packaged AIWACK.exe, real Windows mouse and keyboard."""
import os, sys, time, json, sqlite3, subprocess, tempfile, traceback, shutil
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

def note_input_y(w):
    """Observe the REAL EXE screenshot. A wide white input band exists only on notes page."""
    screen=pyautogui.screenshot().convert("RGB")
    width,height=screen.size
    for y in range(345,475):
        points=[(w.left+x,w.top+y) for x in (180,330,560,790)]
        if any(px<0 or px>=width or py<0 or py>=height for px,py in points):
            continue
        pixels=[screen.getpixel(p) for p in points]
        if all(min(rgb)>210 for rgb in pixels):
            return y
    return None

def open_notes(w):
    # Human operation: physically click a plainly visible button in the packaged EXE.
    # Never mark success merely because the click command returned.
    print("PACKAGED_WINDOW_RECT",w.left,w.top,w.width,w.height,flush=True)
    click(w,370,175)
    snapshot("clicked-notes-button")
    until=time.monotonic()+12
    while time.monotonic()<until:
        field_y=note_input_y(w)
        if field_y is not None:
            print("VISIBLE_NOTES_FIELD at relative y=",field_y,flush=True)
            return field_y + 10  # safe text-entry center within the white band
        time.sleep(.35)
    snapshot("navigation-did-not-show-note")
    raise AssertionError("Clicked EXE notes navigation; actual screen still has no visible notes entry")

def save_button_y(w,field_y):
    screen=pyautogui.screenshot().convert("RGB")
    positions=[]
    for y in range(field_y+37,min(field_y+145,650)):
        x,yabsolute=w.left+125,w.top+y
        if 0 <= x < screen.width and 0 <= yabsolute < screen.height:
            r,g,b=screen.getpixel((x,yabsolute))
            if 45<=r<=130 and 90<=g<=190 and b>=175 and b>g+35:
                positions.append(y)
    if not positions:
        snapshot("save-button-not-visible")
        raise AssertionError("Cannot locate visible blue Save button in real EXE")
    return (positions[0]+positions[-1])//2

def kill_tree(p):
    if p.poll() is None:
        subprocess.run(["taskkill","/T","/F","/PID",str(p.pid)],
          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
        try:p.wait(timeout=10)
        except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)

def test(exe):
    # Keep a separate user data directory. Neither the test nor the EXE is allowed
    # to seed the application DB directly; sqlite3 below is READ-ONLY verification.
    base=Path(tempfile.mkdtemp(prefix="aiwack-packaged-e2e-"))
    d=base/"data"
    db=d/"aiwack.sqlite3"
    process=None
    try:
        process=start(exe,d)
        w=find_window()
        snapshot("first-launch")
        type_text(w,175,320,USER)
        type_text(w,175,401,PASS)
        type_text(w,175,483,PASS)
        snapshot("credentials-typed")
        click(w,175,545)
        expect_db(db,"select username from owner_accounts where id=1",USER)
        snapshot("account-created")
        field_y=open_notes(w)
        snapshot("notes-visible")
        type_text(w,200,field_y,NOTE)
        snapshot("note-typed")
        click(w,130,save_button_y(w,field_y))
        expect_db(db,"select value from system_metadata where key='local_manual_test'",NOTE)
        snapshot("note-saved-in-sqlite")
        shutdown(w,process)
        process=None
        snapshot("exe-closed")

        process=start(exe,d)
        w=find_window()
        snapshot("reopen-login")
        type_text(w,175,395,USER)
        type_text(w,175,437,PASS)
        click(w,175,480)
        time.sleep(2)
        field_y=open_notes(w)
        snapshot("reopen-notes-visible")
        pyperclip.copy("verification-sentinel")
        click(w,200,field_y)
        pyautogui.hotkey("ctrl","a")
        pyautogui.hotkey("ctrl","c")
        time.sleep(.6)
        clipboard=pyperclip.paste()
        assert clipboard==NOTE, "Real EXE display did not show persisted note: "+repr(clipboard)
        snapshot("reopen-note-visible-and-matches")
        click(w,960,175)
        time.sleep(1.1)
        snapshot("user-logged-out")
        shutdown(w,process)
        process=None
        print("PACKAGED_WINDOWS_EXE_REAL_MOUSE_KEYBOARD_PASS",STEPS,flush=True)
    finally:
        if process is not None:
            kill_tree(process)
        # On Windows an EXE may take a moment to release SQLite after exiting.
        # Report cleanup problems without masking the original GUI failure.
        for i in range(12):
            try:
                shutil.rmtree(base)
                break
            except (PermissionError,OSError):
                if i==11:
                    print("WARNING: temporary test data directory remains locked:",base,flush=True)
                else:
                    time.sleep(.5)

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
