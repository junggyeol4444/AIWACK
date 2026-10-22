"""Windows HWND recovery safety unit tests; not physical GUI acceptance."""
import ast
from pathlib import Path
from types import SimpleNamespace


SOURCE = Path(__file__).resolve().parents[2] / "validation" / "windows_packaged_real_gguf_queue_e2e.py"


class FakeWindow:
    def __init__(self, hwnd, title="AIWACK | 로컬 AI 모델 연결"):
        self._hWnd = hwnd
        self.title = title
        self.isMinimized = False

    def activate(self):
        pass

    def restore(self):
        self.isMinimized = False


def _helpers():
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {"_live_window", "_active_is", "_focus_verified"}
    funcs = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name in names]
    assert len(funcs) == 3
    items = []
    current = {"active": None, "valid": {101, 202}, "pids": {101: 11, 202: 11}}
    pgw = SimpleNamespace(getAllWindows=lambda: list(items),
                          getActiveWindow=lambda: current["active"])
    ns = {"_WINDOW_IDENTITY": {}, "_is_window": lambda h: h in current["valid"],
          "_win_pid": lambda h: current["pids"].get(h, 0),
          "pygetwindow": pgw, "time": SimpleNamespace(sleep=lambda *_: None)}
    code = compile(ast.Module(body=funcs, type_ignores=[]), str(SOURCE), "exec")
    exec(code, ns)
    return ns, current, items


def test_valid_window_records_real_process_identity():
    ns, state, windows = _helpers()
    first = FakeWindow(101)
    windows.append(first)
    assert ns["_live_window"](first) is first
    assert ns["_WINDOW_IDENTITY"][101] == (first.title, 11)


def test_stale_hwnd_rebinds_to_same_title_same_process_only():
    ns, state, windows = _helpers()
    old = FakeWindow(101)
    ns["_live_window"](old)
    replacement = FakeWindow(202)
    windows[:] = [replacement]
    state["valid"].remove(101)
    assert ns["_live_window"](old) is replacement


def test_stale_hwnd_refuses_different_pid():
    ns, state, windows = _helpers()
    old = FakeWindow(101)
    ns["_live_window"](old)
    windows[:] = [FakeWindow(202)]
    state["valid"].remove(101)
    state["pids"][202] = 99
    try:
        ns["_live_window"](old)
    except AssertionError:
        pass
    else:
        raise AssertionError("Different-process HWND must not be rebound")


def test_reused_hwnd_refuses_changed_title():
    ns, state, windows = _helpers()
    old = FakeWindow(101)
    ns["_live_window"](old)
    old.title = "Unrelated Application"
    try:
        ns["_live_window"](old)
    except AssertionError:
        pass
    else:
        raise AssertionError("Changed HWND identity must not be accepted")


def test_no_blind_click_to_restore_foreground():
    source = SOURCE.read_text(encoding="utf-8")
    assert "pyautogui.click(w.left + 125, w.top + 18)" not in source
    assert "pyautogui.hotkey(" + '"alt", "f4"' not in source
    assert "_focus_verified(w)" in source
