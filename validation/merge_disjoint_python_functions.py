"""기존 AIWACK Python 소스의 서로 다른 최상위 함수 변경만 원본 보존형 병합.

함수 외 영역(임포트, 클래스, 전역 값, 주석 등)은 세 버전에서 바이트가
동일해야 한다. 함수 삭제·추가·재배치, 동일 함수의 서로 다른 수정은
자동 선택하지 않고 검토 대상으로 보류한다.
"""
from __future__ import annotations

import ast
import hashlib

_MAX_BYTES = 2 * 1024 * 1024


def valid_python_bytes(content: bytes) -> bool:
    """텍스트 병합 결과도 파이썬 문법과 인코딩을 반드시 충족해야 한다."""
    if not isinstance(content, bytes) or not content or len(content) > _MAX_BYTES:
        return False
    if b'\x00' in content or b'\r' in content or content.startswith(b'\xef\xbb\xbf'):
        return False
    try:
        ast.parse(content.decode('utf-8'), type_comments=True)
    except (UnicodeError, SyntaxError, ValueError, MemoryError):
        return False
    return True


def _parts(content: bytes):
    if not valid_python_bytes(content):
        return None
    source = content.decode('utf-8')
    tree = ast.parse(source, type_comments=True)
    lines = content.splitlines(keepends=True)
    definitions = [node for node in tree.body
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if not definitions:
        return None
    names = [(type(node).__name__, node.name) for node in definitions]
    if len(set(names)) != len(names):
        return None
    spans = []
    for node in definitions:
        start = min([node.lineno] + [decorator.lineno for decorator in node.decorator_list]) - 1
        end = node.end_lineno
        if not (0 <= start < end <= len(lines)):
            return None
        spans.append((start, end))
    outside, bodies = [], []
    last = 0
    for start, end in spans:
        if start < last:
            return None
        outside.append(b''.join(lines[last:start]))
        bodies.append(b''.join(lines[start:end]))
        last = end
    outside.append(b''.join(lines[last:]))
    return names, outside, bodies


def merge_disjoint_python_functions(base: bytes, main: bytes, test: bytes) -> dict | None:
    """함수 단위 독립 변경만 합치고 원본 SHA 및 변경 함수 출처를 반환한다."""
    if not all(isinstance(x, bytes) for x in (base, main, test)):
        return None
    original = _parts(base)
    left = _parts(main)
    right = _parts(test)
    if not original or not left or not right:
        return None
    base_names, base_outside, base_bodies = original
    main_names, main_outside, main_bodies = left
    test_names, test_outside, test_bodies = right
    if (base_names != main_names or base_names != test_names
            or base_outside != main_outside or base_outside != test_outside):
        return None
    merged = bytearray(base_outside[0])
    from_main, from_test, shared = [], [], []
    for i, (name, b, m, t) in enumerate(zip(base_names, base_bodies, main_bodies, test_bodies)):
        if m != b and t != b and m != t:
            return None
        if m != b and t == b:
            chosen = m
            from_main.append(name[1])
        elif t != b and m == b:
            chosen = t
            from_test.append(name[1])
        elif m == t and m != b:
            chosen = m
            shared.append(name[1])
        else:
            chosen = b
        merged.extend(chosen)
        merged.extend(base_outside[i + 1])
    output = bytes(merged)
    if not valid_python_bytes(output):
        return None
    if not from_main or not from_test:
        return None
    return {
        'content': output,
        'sha256': hashlib.sha256(output).hexdigest(),
        'base_sha256': hashlib.sha256(base).hexdigest(),
        'main_sha256': hashlib.sha256(main).hexdigest(),
        'test_sha256': hashlib.sha256(test).hexdigest(),
        'merge_policy': 'python_disjoint_top_level_functions',
        'main_changed_functions': from_main,
        'test_changed_functions': from_test,
        'identical_changed_functions': shared,
    }
