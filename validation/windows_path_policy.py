"""AIWACK 누적 소스 ZIP/매니페스트 Windows 10/11 파일명 안전 규칙.

읽기 전용 검사에서만 사용하며 원본 이름을 정규화하거나 변경하지 않는다.
"""
from __future__ import annotations

import unicodedata

FORBIDDEN = frozenset('<>:"|?*')
RESERVED = frozenset({'CON', 'PRN', 'AUX', 'NUL'} | {
    f'{prefix}{number}' for prefix in ('COM', 'LPT') for number in range(1, 10)
})


def collision_key(path: str) -> str:
    """NFC + casefold: Windows에서 충돌할 수 있는 경로를 보수적으로 탐지."""
    return unicodedata.normalize('NFC', path).casefold()


def unsafe_part(part: str) -> str | None:
    """Windows에서 생성할 수 없는 구성 요소를 이유 코드로 반환."""
    if (not part or part in ('.', '..') or part.endswith((' ', '.'))
            or any(ord(ch) < 32 or ch in FORBIDDEN for ch in part)):
        return 'windows_invalid_name'
    if part.split('.', 1)[0].upper() in RESERVED:
        return 'windows_reserved_name'
    return None
