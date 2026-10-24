"""Guarded Windows HWND recovery regressions; AST-only, not physical GUI proof.

The original 21st-round test is retained unchanged inside preservation ZIP.
This updated fixture exercises the complete current focus/PID/identity guard path.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import pytest

SOURCE = Path(__file__).with_name('windows_packaged_real_gguf_queue_e2e.py')

class Window:
    def __init__(self, handle, title, *, stale=False):
        self._hWnd=handle; self._title=title; self.stale=stale
        self.isMinimized=False; self.left=100; self.top=200
        self.closed=False
    @property
    def title(self):
        if self.stale: raise RuntimeError('Windows 1400 - invalid window handle')
        return self._title
    @property
    def width(self):
        if self.stale: raise RuntimeError('Windows 1400 - invalid window handle')
        return 900
    @property
    def height(self):
        if self.stale: raise RuntimeError('Windows 1400 - invalid window handle')
        return 700
    def activate(self):
        if self.stale: raise RuntimeError('Windows 1400 - invalid window handle')
    def restore(self): self.isMinimized=False
    def close(self): self.closed=True

def load_window_helpers(frames, *, active=None):
    tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
    names={'_owner_pid','_live_window','_visible_window','_stable_native_rect','_focus_verified',
           '_active_is','click','close_dialog_safely','find_dialog'}
    body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in body} == names
    code=compile(ast.fix_missing_locations(ast.Module(body=body,type_ignores=[])),str(SOURCE),'exec')
    calls=[]
    windows=[frames[-1] if isinstance(frames[-1],list) else []]
    def enumerate_windows():
        item=frames.pop(0) if len(frames)>1 else frames[0]
        if isinstance(item,Exception):raise item
        windows[0]=item
        return item
    def current_active():
        return active[0] if active is not None else (windows[0][0] if windows[0] else None)
    gui=SimpleNamespace(getAllWindows=enumerate_windows,getActiveWindow=current_active)
    mouse=SimpleNamespace(click=lambda *args:calls.append(('click',args)),
                          hotkey=lambda *args:calls.append(('hotkey',args)))
    from itertools import count
    ticker=count()
    ctx={'_WINDOW_IDENTITY':{},'_TARGET_EXE_PID':None,
         'WINDOW_TITLES':{},'WINDOW_PIDS':{},
         '_native_window_pid':lambda hwnd:100,
         '_is_window':lambda hwnd:int(hwnd)!=10,
         '_win_pid':lambda hwnd:100,
         'os':SimpleNamespace(name='posix'),
         'pygetwindow':gui,'pyautogui':mouse,
         'time':SimpleNamespace(sleep=lambda *_:None,monotonic=lambda:next(ticker)*.10),
         'evidence':lambda stage:calls.append(('evidence',stage))}
    exec(code,ctx)
    return ctx,calls

def test_win32_1400_cached_handle_reacquired_with_same_pid_before_click():
    old=Window(10,'AIWACK',stale=True); new=Window(11,'AIWACK')
    ctx,calls=load_window_helpers([[new]],active=[new])
    ctx['_WINDOW_IDENTITY'][10]=('AIWACK',100)
    ctx['WINDOW_TITLES'][10]='AIWACK';ctx['WINDOW_PIDS']['AIWACK']=100
    ctx['click'](old,125,330)
    assert ('click',(225,530)) in calls
    assert ctx['_WINDOW_IDENTITY'][11] == ('AIWACK',100)

def test_missing_modal_refuses_close_or_main_window_alt_f4():
    old=Window(10,'AIWACK | 로컬 AI 모델 연결',stale=True)
    main=Window(20,'AIWACK')
    ctx,calls=load_window_helpers([[main]],active=[main])
    ctx['_WINDOW_IDENTITY'][10]=('AIWACK | 로컬 AI 모델 연결',100)
    ctx['WINDOW_TITLES'][10]='AIWACK | 로컬 AI 모델 연결'
    ctx['WINDOW_PIDS']['AIWACK | 로컬 AI 모델 연결']=100
    with pytest.raises(AssertionError):
        ctx['close_dialog_safely'](old,'AIWACK | 로컬 AI 모델 연결')
    assert not main.closed
    assert not any(c[0] in ('click','hotkey') for c in calls)

def test_ambiguous_same_pid_windows_never_click():
    old=Window(10,'AIWACK',stale=True)
    a=Window(11,'AIWACK');b=Window(12,'AIWACK')
    ctx,calls=load_window_helpers([[a,b]],active=[a])
    ctx['_WINDOW_IDENTITY'][10]=('AIWACK',100)
    ctx['WINDOW_TITLES'][10]='AIWACK';ctx['WINDOW_PIDS']['AIWACK']=100
    with pytest.raises(AssertionError):ctx['click'](old,125,330)
    assert not any(c[0]=='click' for c in calls)

def test_dialog_enumeration_transient_1400_retries_without_blind_click():
    dialog=Window(41,'AIWACK | 로컬 AI 모델 연결')
    ctx,calls=load_window_helpers([RuntimeError('Win32 1400'),[dialog]],active=[dialog])
    assert ctx['find_dialog']('AIWACK | 로컬 AI 모델 연결',timeout=2) is dialog
    assert not any(c[0]=='click' for c in calls)

def test_focus_guard_refuses_foreign_foreground_without_click():
    target=Window(41,'AIWACK | 로컬 AI 모델 연결')
    foreign=Window(99,'다른 프로그램')
    ctx,calls=load_window_helpers([[target]],active=[foreign])
    with pytest.raises(AssertionError,match='foreground'):
        ctx['click'](target,120,320)
    assert not any(c[0]=='click' for c in calls)

class ShortNativePrompt(Window):
    """Physical Windows Server 2025 Tk simpledialog screenshot: 353 x 128."""
    @property
    def width(self): return 353
    @property
    def height(self): return 128

def test_short_verified_chief_input_dialog_survives_native_size_filter():
    modal=ShortNativePrompt(51,'총괄 AI → 직원 업무 지휘')
    ctx,calls=load_window_helpers([[modal]],active=[modal])
    ctx['_TARGET_EXE_PID']=100
    assert ctx['find_dialog']('총괄 AI → 직원 업무 지휘',timeout=3) is modal
    assert not any(c[0]=='click' for c in calls)

def test_unrelated_small_native_window_cannot_be_mistaken_for_chief_modal():
    foreign=ShortNativePrompt(52,'관련 없는 창')
    ctx,calls=load_window_helpers([[foreign]],active=[foreign])
    ctx['_TARGET_EXE_PID']=100
    with pytest.raises(AssertionError,match='not found'):
        ctx['find_dialog']('총괄 AI → 직원 업무 지휘',timeout=1)
    assert not any(c[0]=='click' for c in calls)
