"""AIWACK 과거 JSON 원본의 서로 독립적인 키 변경을 보존형으로 병합한다.

원본·main·테스트 바이트는 절대 수정하지 않는다. 실제 SHA 검증된
단일 과거 버전을 호출자가 제공할 때만 사용하며, 충돌/모호성은 보류한다.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

_MAX_BYTES = 2 * 1024 * 1024
_MISSING = object()
_CONFLICT = object()


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('JSON 중복 키: ' + key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError('비표준 JSON 숫자: ' + value)


def _decode(data: bytes) -> dict:
    if not isinstance(data, bytes) or len(data) > _MAX_BYTES or b'\x00' in data:
        raise ValueError('JSON 파일 크기·형식 오류')
    result = json.loads(data.decode('utf-8'), object_pairs_hook=_unique_pairs,
                        parse_constant=_reject_constant)
    if not isinstance(result, dict):
        raise ValueError('최상위 JSON 객체만 자동 병합합니다.')
    return result


def _same(a: Any, b: Any) -> bool:
    if a is _MISSING or b is _MISSING:
        return a is b
    return json.dumps(a, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')) == json.dumps(
                          b, sort_keys=True, ensure_ascii=False, allow_nan=False,
                          separators=(',', ':'))


def _merge(base: Any, main: Any, test: Any) -> Any:
    if _same(main, test):
        return main
    if _same(main, base):
        return test
    if _same(test, base):
        return main
    if (isinstance(base, dict) and isinstance(main, dict)
            and isinstance(test, dict)):
        merged = {}
        for key in dict.fromkeys([*base, *main, *test]):
            value = _merge(base.get(key, _MISSING), main.get(key, _MISSING),
                           test.get(key, _MISSING))
            if value is _CONFLICT:
                return _CONFLICT
            if value is not _MISSING:
                merged[key] = value
        return merged
    return _CONFLICT


def merge_disjoint_json(base: bytes, main: bytes, test: bytes) -> dict | None:
    """중첩 객체의 독립 키 변경만 결합한다. 충돌·파싱 실패 시 None."""
    try:
        old, left, right = (_decode(raw) for raw in (base, main, test))
        if _same(old, left) or _same(old, right):
            return None
        merged = _merge(old, left, right)
        if merged is _CONFLICT:
            return None
        content = (json.dumps(merged, ensure_ascii=False, indent=2,
                              allow_nan=False) + '\n').encode('utf-8')
    except (ValueError, UnicodeError, TypeError, RecursionError, OverflowError):
        return None
    return {'content': content, 'sha256': hashlib.sha256(content).hexdigest(),
            'base_sha256': hashlib.sha256(base).hexdigest(),
            'main_sha256': hashlib.sha256(main).hexdigest(),
            'test_sha256': hashlib.sha256(test).hexdigest(),
            'merge_kind': 'disjoint_json_keys'}
