"""기존 Windows EXE 검사기의 창 대상 지정 안전성만 검증하는 보조 테스트.

실제 Windows 클릭·Tk 로그인·GGUF 모델 실측을 대신하지 않는다.
"""
from __future__ import annotations

import ast
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / 'validation' / 'windows_packaged_real_gguf_queue_e2e.py'


def _closure_namespace(dialogs, evidence_events):
    tree = ast.parse(SCRIPT.read_text(encoding='utf-8'))
    close_def = next(x for x in tree.body if isinstance(x, ast.FunctionDef)
                     and x.name == 'close_dialog_safely')
    scope = {'time': time, 'evidence': evidence_events.append,
             '_visible_window': lambda w: w,
             'pygetwindow': SimpleNamespace(getAllWindows=lambda: list(dialogs))}
    exec(compile(ast.Module(body=[close_def], type_ignores=[]), str(SCRIPT), 'exec'), scope)
    return scope['close_dialog_safely']


class NativeWindow:
    def __init__(self, title, handle, dialogs):
        self.title = title
        self._hWnd = handle
        self._dialogs = dialogs
        self.closed = False

    def close(self):
        self.closed = True
        self._dialogs.remove(self)


def test_close_targets_modal_without_closing_main_window():
    dialogs = []
    main = NativeWindow('AIWACK - 기존 회사 대시보드', 1, dialogs)
    modal = NativeWindow('AIWACK | 로컬 AI 직원 모델 호출 진단', 2, dialogs)
    dialogs.extend((main, modal))
    close = _closure_namespace(dialogs, [])
    assert close(modal, 'AIWACK | 로컬 AI 직원 모델 호출 진단') is True
    assert modal.closed and not main.closed and dialogs == [main]


def test_close_refuses_main_window_even_if_it_is_focused():
    dialogs = []
    main = NativeWindow('AIWACK - 기존 회사 대시보드', 1, dialogs)
    dialogs.append(main)
    close = _closure_namespace(dialogs, [])
    with pytest.raises(AssertionError, match='different Windows window'):
        close(main, 'AIWACK | 로컬 AI 모델 연결')
    assert not main.closed


def _geometry_helper(window_provider):
    tree=ast.parse(SCRIPT.read_text(encoding='utf-8'))
    func=next(x for x in tree.body if isinstance(x,ast.FunctionDef)
              and x.name=='_stable_native_rect')
    events=[]
    scope={'_visible_window':window_provider,'time':SimpleNamespace(sleep=lambda _:None),
           'evidence':events.append}
    exec(compile(ast.Module(body=[func],type_ignores=[]),str(SCRIPT),'exec'),scope)
    return scope['_stable_native_rect'],events


def test_native_geometry_reacquires_after_windows_1400_during_property_read():
    class Invalid:
        _hWnd=22
        title='AIWACK | 로컬 AI 모델 연결'
        left=100
        top=100
        @property
        def width(self):
            raise OSError('Windows 1400 Invalid window handle')
    valid=SimpleNamespace(_hWnd=23,title='AIWACK | 로컬 AI 모델 연결',
                          left=100,top=110,width=650,height=550)
    count=[0]
    def provider(_):
        count[0]+=1
        return Invalid() if count[0]==1 else valid
    helper,events=_geometry_helper(provider)
    found,rect=helper(valid)
    assert found is valid and rect==(100,110,650,550)
    assert count[0]==2 and not events


def test_native_geometry_rejects_repeated_invalid_handles_without_click():
    class Invalid:
        _hWnd=22
        title='AIWACK | 로컬 AI 모델 연결'
        left=100
        top=100
        @property
        def width(self):
            raise OSError('Windows 1400 Invalid window handle')
    helper,events=_geometry_helper(lambda _:Invalid())
    with pytest.raises(AssertionError,match='geometry changed'):
        helper(None)
    assert events==['native-window-geometry-unstable']
