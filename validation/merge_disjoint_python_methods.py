"""AIWACK 원본 Python의 서로 다른 클래스 메서드/최상위 함수 변경만 안전 병합.

동일 원본의 함수·메서드 영역만 변경 가능하다. 클래스 정의, 상속,
데코레이터, 전역문, 임포트, 클래스 변수, 주석 등 다른 모든 바이트는
원본·main·테스트가 동일해야 하며 모호한 변경은 자동 병합하지 않는다.
"""
from __future__ import annotations

import ast
import hashlib

try:
    from validation.merge_disjoint_python_functions import valid_python_bytes
except ImportError:
    from merge_disjoint_python_functions import valid_python_bytes


def _parts(content: bytes):
    if not valid_python_bytes(content):
        return None
    tree = ast.parse(content.decode('utf-8'), type_comments=True)
    lines = content.splitlines(keepends=True)
    spans = []
    top_names = set()
    class_names = set()
    has_method = False
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in top_names:
                return None
            top_names.add(node.name)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
            spans.append((start, node.end_lineno, type(node).__name__, node.name))
        elif isinstance(node, ast.ClassDef):
            if node.name in class_names:
                return None
            class_names.add(node.name)
            method_names = set()
            for child in node.body:
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if child.name in method_names:
                    return None
                method_names.add(child.name)
                has_method = True
                start = min([child.lineno] + [d.lineno for d in child.decorator_list]) - 1
                if start <= node.lineno - 1 or child.end_lineno > node.end_lineno:
                    return None
                spans.append((start, child.end_lineno, type(child).__name__,
                              node.name + '.' + child.name))
    if not has_method:
        return None
    spans.sort(key=lambda item: item[0])
    names, outside, bodies = [], [], []
    previous = 0
    for start, end, kind, name in spans:
        if not (previous <= start < end <= len(lines)):
            return None
        outside.append(b''.join(lines[previous:start]))
        bodies.append(b''.join(lines[start:end]))
        names.append((kind, name))
        previous = end
    outside.append(b''.join(lines[previous:]))
    if len(set(names)) != len(names):
        return None
    return names, outside, bodies


def merge_disjoint_python_methods(base: bytes, main: bytes, test: bytes) -> dict | None:
    """기존 세 파일을 변경하지 않고 독립 메서드 변경만 병합한 증빙을 반환한다."""
    if not all(isinstance(x, bytes) for x in (base, main, test)):
        return None
    original, left, right = (_parts(x) for x in (base, main, test))
    if not original or not left or not right:
        return None
    names, outside, bodies = original
    if (names != left[0] or names != right[0]
            or outside != left[1] or outside != right[1]):
        return None
    result = bytearray(outside[0])
    from_main, from_test, shared = [], [], []
    for i, (_, name) in enumerate(names):
        old, m, t = bodies[i], left[2][i], right[2][i]
        if m != old and t != old and m != t:
            return None
        if m != old and t == old:
            chosen = m
            from_main.append(name)
        elif t != old and m == old:
            chosen = t
            from_test.append(name)
        elif m == t and m != old:
            chosen = m
            shared.append(name)
        else:
            chosen = old
        result.extend(chosen)
        result.extend(outside[i + 1])
    merged = bytes(result)
    if not from_main or not from_test or not valid_python_bytes(merged):
        return None
    return {
        'content': merged,
        'sha256': hashlib.sha256(merged).hexdigest(),
        'base_sha256': hashlib.sha256(base).hexdigest(),
        'main_sha256': hashlib.sha256(main).hexdigest(),
        'test_sha256': hashlib.sha256(test).hexdigest(),
        'merge_policy': 'python_disjoint_class_methods_and_functions',
        'main_changed_functions': from_main,
        'test_changed_functions': from_test,
        'identical_changed_functions': shared,
    }
