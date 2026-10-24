"""원본을 덮어쓰지 않고 독립적인 인수인계 추가 기록을 3-way 병합한다.

양쪽 파일이 검증된 동일 원문을 바이트 단위 접두부로 보존한 경우에만
서로 다른 회차의 완결된 섹션을 순서대로 연결한다. 기존 섹션 수정,
같은 섹션 제목의 충돌, 인코딩·크기 오류는 자동 병합하지 않는다.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath

_MAX_BYTES = 2 * 1024 * 1024
_SECTION = re.compile(r'(?m)^##[ \t]+([^\r\n]+)[ \t]*\r?$')


def is_append_only_handoff_path(path: str) -> bool:
    """기존 AIWACK 인수인계 문서에만 제한적으로 적용한다."""
    if not isinstance(path, str) or '\\' in path or '\x00' in path:
        return False
    pure = PurePosixPath(path)
    if (not path.startswith('docs/') or pure.is_absolute()
            or '..' in pure.parts or pure.suffix.lower() != '.md'):
        return False
    return ('인수인계' in pure.name or pure.name == 'automation_full_handoff.md')


def _sections(suffix: str) -> set[str] | None:
    if not suffix.strip():
        return None
    if not suffix.lstrip('\r\n').startswith('## '):
        return None
    headings = [m.group(1).strip() for m in _SECTION.finditer(suffix)]
    if not headings or len(headings) != len(set(headings)):
        return None
    return set(headings)


def merge_append_only_handoffs(path: str, base: bytes, main: bytes,
                               test: bytes) -> dict | None:
    """검증된 동일 접두부 뒤에 붙인 독립 섹션만 보존형으로 합친다."""
    if not is_append_only_handoff_path(path):
        return None
    if any(not isinstance(x, bytes) or len(x) > _MAX_BYTES or b'\x00' in x
           for x in (base, main, test)):
        return None
    if not base or not base.endswith(b'\n') or not main.startswith(base) or not test.startswith(base):
        return None
    left, right = main[len(base):], test[len(base):]
    if not left or not right:
        return None
    try:
        base.decode('utf-8')
        left_text, right_text = left.decode('utf-8'), right.decode('utf-8')
    except UnicodeDecodeError:
        return None
    left_titles, right_titles = _sections(left_text), _sections(right_text)
    if left_titles is None or right_titles is None:
        return None
    if left == right:
        merged = main
    elif left.startswith(right):
        merged = main
    elif right.startswith(left):
        merged = test
    else:
        if left_titles & right_titles:
            return None
        merged = base + left + (b'\n' if not left.endswith(b'\n') else b'') + right
    if len(merged) > _MAX_BYTES:
        return None
    return {'content': merged, 'sha256': hashlib.sha256(merged).hexdigest(),
            'base_sha256': hashlib.sha256(base).hexdigest(),
            'main_sha256': hashlib.sha256(main).hexdigest(),
            'test_sha256': hashlib.sha256(test).hexdigest(),
            'main_appended_bytes': len(left), 'test_appended_bytes': len(right),
            'merge_policy': 'append_only_distinct_sections',
            'source_order': ['original', 'main_append', 'test_append']}
