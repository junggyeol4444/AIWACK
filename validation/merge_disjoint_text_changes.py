"""과거 원본·main·테스트의 비중첩 텍스트 수정만 SHA 증빙과 함께 결합한다."""
from __future__ import annotations
from difflib import SequenceMatcher
from hashlib import sha256

_MAX_TEXT_BYTES = 2 * 1024 * 1024


def _text_lines(data: bytes) -> list[str] | None:
    if not isinstance(data, bytes) or len(data) > _MAX_TEXT_BYTES or b'\0' in data:
        return None
    try:
        value = data.decode('utf-8')
    except UnicodeDecodeError:
        return None
    return value.splitlines(keepends=True)


def _edits(original: list[str], changed: list[str]) -> list[tuple[int, int, list[str]]]:
    return [(i1, i2, changed[j1:j2])
            for tag, i1, i2, j1, j2 in SequenceMatcher(
                None, original, changed, autojunk=False).get_opcodes() if tag != 'equal']


def _overlap(a: tuple, b: tuple) -> bool:
    a1, a2, _ = a
    b1, b2, _ = b
    if a1 == a2 and b1 == b2:
        return a1 == b1
    if a1 == a2:
        return b1 <= a1 <= b2
    if b1 == b2:
        return a1 <= b1 <= a2
    return max(a1, b1) < min(a2, b2)


def merge_disjoint_text(base: bytes, main: bytes, test: bytes) -> dict | None:
    """실제 비중첩 변경만 병합하고 겹침·바이너리·손상 텍스트는 보류한다."""
    originals = [_text_lines(raw) for raw in (base, main, test)]
    if any(lines is None for lines in originals):
        return None
    original_lines, main_lines, test_lines = originals
    main_edits = _edits(original_lines, main_lines)
    test_edits = _edits(original_lines, test_lines)
    if not main_edits or not test_edits:
        return None
    if any(_overlap(a, b) for a in main_edits for b in test_edits):
        return None
    merged = original_lines[:]
    for start, end, replacement in sorted(main_edits + test_edits,
                                          key=lambda item: (item[0], item[1]), reverse=True):
        merged[start:end] = replacement
    data = ''.join(merged).encode('utf-8')
    return {'content': data, 'sha256': sha256(data).hexdigest(),
            'main_edits': len(main_edits), 'test_edits': len(test_edits),
            'base_sha256': sha256(base).hexdigest()}
