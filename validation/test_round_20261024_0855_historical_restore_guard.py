"""원본 복원 도중 링크·과대 파일이 자동 병합되지 않는지 확인."""
import hashlib

from validation.restore_missing_historical import verified_historical_recovery


def _item(path, raw):
    return {'path': path, 'classification': 'missing_in_both',
            'main_sha256': None, 'test_sha256': None,
            'historical_sha256': [hashlib.sha256(raw).hexdigest()]}


def test_parent_symlink_inside_historical_root_is_held(tmp_path):
    actual = tmp_path / 'actual'
    actual.mkdir()
    (actual / 'history.txt').write_bytes(b'original')
    (tmp_path / 'alias').symlink_to(actual, target_is_directory=True)
    assert verified_historical_recovery(
        _item('alias/history.txt', b'original'), tmp_path) is None


def test_large_historical_file_is_held_without_reading(tmp_path):
    source = tmp_path / 'large.bin'
    with source.open('wb') as output:
        output.truncate(32 * 1024 * 1024 + 1)
    assert verified_historical_recovery(
        _item('large.bin', b'not-the-content'), tmp_path) is None


def test_regular_small_file_still_recovers_exact_bytes(tmp_path):
    raw = b'original'
    (tmp_path / 'safe.txt').write_bytes(raw)
    result = verified_historical_recovery(_item('safe.txt', raw), tmp_path)
    assert result is not None
    assert result['content'] == raw
    assert result['sha256'] == hashlib.sha256(raw).hexdigest()
