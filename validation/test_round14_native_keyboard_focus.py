"""Windows EXE 키보드 타깃 검증 구조 회귀. 실제 Windows 클릭 아님."""
import ast
from pathlib import Path
from types import SimpleNamespace
import pytest

SOURCE=Path(__file__).with_name('windows_packaged_real_gguf_queue_e2e.py')

class FakeWindow:
    _hWnd=42
    title='AIWACK | 모델 연결'
    width=800
    height=600
    left=20
    top=30
    isMinimized=False

def _load(active):
    tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
    functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and
               node.name in {'_verify_native_keyboard_focus','write'}]
    events=[]
    window=FakeWindow()
    context={'_stable_native_rect':lambda w:(window,(20,30,800,600)),
             'pygetwindow':SimpleNamespace(getActiveWindow=lambda:active()),
             'pyautogui':SimpleNamespace(hotkey=lambda *args:events.append('select'),
                                         write=lambda *args,**kw:events.append('type')),
             'click':lambda *args:events.append('click'),
             'os':SimpleNamespace(name='posix')}
    exec(compile(ast.fix_missing_locations(ast.Module(body=functions,type_ignores=[])),
                 str(SOURCE),'exec'),context)
    return context,events,window

def test_typing_when_native_modal_stays_foreground():
    target=FakeWindow()
    ctx,events,_=_load(lambda:target)
    ctx['write'](target,50,100,'owner-test')
    assert events==['click','select','type']

def test_foreground_switch_after_click_never_selects_or_types():
    ctx,events,target=_load(lambda:SimpleNamespace(_hWnd=99))
    with pytest.raises(AssertionError,match='lost foreground'):
        ctx['write'](target,50,100,'owner-test')
    assert events==['click']

def test_foreground_switch_after_select_never_types():
    holder={'active':FakeWindow()}
    ctx,events,target=_load(lambda:holder['active'])
    def switch_after_select(*args):
        events.append('select')
        holder['active']=SimpleNamespace(_hWnd=99)
    ctx['pyautogui'].hotkey=switch_after_select
    with pytest.raises(AssertionError,match='lost foreground'):
        ctx['write'](target,50,100,'owner-test')
    assert events==['click','select']