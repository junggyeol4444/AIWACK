"""기존 main에 이미 보존된 변경과 실제 미병합 변경을 구분한다.

원본 이력의 모호함이나 파일 손실을 자동 해결하지 않는다.
"""
from __future__ import annotations


def is_preserved_in_main(item: dict) -> bool:
    """추가 쓰기 없이 main 복사만으로 보존되는 검토 항목인지 판정한다."""
    status = item.get('classification')
    main_sha = item.get('main_sha256')
    test_sha = item.get('test_sha256')
    history = item.get('historical_sha256')
    if not isinstance(history, list):
        raise ValueError('과거 원본 SHA 목록이 없습니다.')
    if status == 'main_only':
        if not main_sha or test_sha is not None:
            raise ValueError('main 전용 변경의 감사 결과가 일치하지 않습니다.')
        return True
    if status == 'main_changed_from_original':
        if not main_sha or test_sha not in history or main_sha in history:
            raise ValueError('main 변경의 원본 기준이 일치하지 않습니다.')
        return True
    if status == 'same_in_both':
        if not main_sha or main_sha != test_sha:
            raise ValueError('동일 변경의 감사 결과가 일치하지 않습니다.')
        return True
    return False
