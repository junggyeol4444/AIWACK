"""역사 원본 복원: 전체 목적지 사전 검사 후 부분 쓰기 금지."""
import zipfile
import pytest
from validation.restore_original_source_history import reconcile


def test_late_symlink_does_not_leave_first_file(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    try:
        (root / 'z-later').symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('현재 환경에서 심볼릭 링크 생성 불가')
    archive = tmp_path / 'original.zip'
    with zipfile.ZipFile(archive, 'w') as out:
        out.writestr('a-first/original.txt', 'must not be written')
        out.writestr('z-later/unsafe.txt', 'blocked')
    with pytest.raises(ValueError, match='링크 경로'):
        reconcile(archive, root, restore_missing=True)
    assert not (root / 'a-first').exists()
    assert not (outside / 'unsafe.txt').exists()
