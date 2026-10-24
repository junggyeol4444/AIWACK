"""기존 AIWACK Python의 서로 다른 최상위 클래스·함수 변경을 원본 보존 병합.

세 버전의 임포트·전역문·주석 등 정의 바깥 영역이 바이트 단위로 같고,
동일 정의가 양쪽에서 상충 변경되지 않을 때만 병합한다. 클래스 내부는
독립 메서드로 추정하지 않고 클래스 전체를 하나의 변경 단위로 취급한다.
"""
from __future__ import annotations

import ast
import hashlib

try:
    from validation.merge_disjoint_python_functions import valid_python_bytes
except ImportError:
    from merge_disjoint_python_functions import valid_python_bytes


_BLOCKS = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _split_blocks(content: bytes):
    if not valid_python_bytes(content):
        return None
    tree = ast.parse(content.decode('utf-8'), type_comments=True)
    lines = content.splitlines(keepends=True)
    spans = []
    seen = set()
    for node in tree.body:
        if not isinstance(node, _BLOCKS):
            continue
        # 같은 이름의 클래스·함수 재정의는 순서에 따라 의미가 달라지므로 보류.
        if node.name in seen:
            return None
        seen.add(node.name)
        decorators = [d.lineno for d in getattr(node, 'decorator_list', ())]
        start = min([node.lineno] + decorators) - 1
        end = node.end_lineno
        if not (0 <= start < end <= len(lines)):
            return None
        spans.append((start, end, type(node).__name__, node.name))
    if len(spans) < 2:
        return None
    names, outside, blocks = [], [], []
    previous = 0
    for start, end, kind, name in spans:
        if start < previous:
            return None
        outside.append(b''.join(lines[previous:start]))
        blocks.append(b''.join(lines[start:end]))
        names.append((kind, name))
        previous = end
    outside.append(b''.join(lines[previous:]))
    return names, outside, blocks


def merge_disjoint_python_blocks(base: bytes, main: bytes, test: bytes) -> dict | None:
    """독립 최상위 정의를 병합하되 원본 3개와 변경 출처 SHA256을 유지한다."""
    if not all(isinstance(value, bytes) for value in (base, main, test)):
        return None
    parts = [_split_blocks(value) for value in (base, main, test)]
    if any(part is None for part in parts):
        return None
    original, left, right = parts
    names, outside, blocks = original
    if names != left[0] or names != right[0] or outside != left[1] or outside != right[1]:
        return None
    result = bytearray(outside[0])
    changed_main, changed_test, identical = [], [], []
    for i, (_, name) in enumerate(names):
        b, m, t = blocks[i], left[2][i], right[2][i]
        if m != b and t != b and m != t:
            return None
        if m != b and t == b:
            chosen = m
            changed_main.append(name)
        elif t != b and m == b:
            chosen = t
            changed_test.append(name)
        elif m == t and m != b:
            chosen = m
            identical.append(name)
        else:
            chosen = b
        result.extend(chosen)
        result.extend(outside[i + 1])
    merged = bytes(result)
    if not changed_main or not changed_test or not valid_python_bytes(merged):
        return None
    return {
        'content': merged,
        'sha256': hashlib.sha256(merged).hexdigest(),
        'base_sha256': hashlib.sha256(base).hexdigest(),
        'main_sha256': hashlib.sha256(main).hexdigest(),
        'test_sha256': hashlib.sha256(test).hexdigest(),
        'merge_policy': 'python_disjoint_top_level_classes_and_functions',
        'main_changed_blocks': changed_main,
        'test_changed_blocks': changed_test,
        'identical_changed_blocks': identical,
    }
