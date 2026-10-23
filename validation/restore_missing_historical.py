"""AIWACK 원본 전수 감사에서 확인된 누락 파일을 별도 병합 폴더에 복원한다.

기존 main·테스트·역사 원본은 읽기 전용이며, SHA256 단일 버전만 인정한다.
과거 원본을 임의 선택하거나 원본 폴더에 파일을 쓰지 않는다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

try:
    from validation.windows_path_policy import unsafe_part
except ImportError:
    from windows_path_policy import unsafe_part


def verified_historical_recovery(item: dict, historical_root: Path) -> dict | None:
    """main에 없는 파일을 검증된 단일 역사 원본으로만 복원한다.

    missing_in_both: main/test 양쪽에서 삭제된 역사 파일.
    test_only: main에 없지만 테스트 파일이 역사 원본과 동일한 경우.
    그 외·SHA 불일치·다중버전·심볼릭 링크는 보류(None).
    """
    if not isinstance(item, dict):
        return None
    status = item.get('classification')
    if status not in ('missing_in_both', 'test_only'):
        return None
    if item.get('main_sha256') is not None:
        return None
    hashes = item.get('historical_sha256')
    if not isinstance(hashes, list) or len(hashes) != 1:
        return None
    expected = hashes[0]
    if (not isinstance(expected, str) or len(expected) != 64
            or any(c not in '0123456789abcdef' for c in expected)):
        return None
    if status == 'missing_in_both' and item.get('test_sha256') is not None:
        return None
    if status == 'test_only' and item.get('test_sha256') != expected:
        return None
    relative = item.get('path')
    if not isinstance(relative, str) or not relative:
        return None
    path = PurePosixPath(relative)
    if (path.is_absolute() or str(path) != relative or
            any(part in ('.', '..') or unsafe_part(part) for part in path.parts)):
        return None
    root = Path(historical_root).resolve(strict=True)
    source = root.joinpath(*path.parts)
    if not source.is_file() or source.is_symlink():
        return None
    if not source.resolve().is_relative_to(root):
        return None
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        return None
    return {
        'content': data, 'sha256': digest,
        'historical_sha256': expected,
        'restore_kind': 'verified_single_historical',
        'classification': status,
    }
