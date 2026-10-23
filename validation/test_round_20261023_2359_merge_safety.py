"""Windows 원본 보존 병합의 동시 변경·금지 경로 회귀."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from validation import stage_three_way_merge as stage_module
from validation.stage_three_way_merge import stage_merge
from validation.three_way_merge_review import _snapshot


def _audit(original: bytes):
    return {
        'coverage_confirmed': True,
        'identical': [{'path': 'core.py', 'original_versions': [
            {'sha256': hashlib.sha256(original).hexdigest()}]}],
        'changed': [], 'missing': [], 'version_conflicts': [],
    }


def _roots(tmp_path):
    main, test = tmp_path / 'main', tmp_path / 'test'
    main.mkdir(); test.mkdir()
    (main / 'core.py').write_bytes(b'base\n')
    (test / 'core.py').write_bytes(b'updated\n')
    return main, test


@pytest.mark.parametrize('bad_name', ['NUL.txt', 'CON', 'file ', 'bad:name.txt', 'LPT1.log'])
def test_windows_unsafe_filename_blocks_all_staging(tmp_path, bad_name):
    main, test = _roots(tmp_path)
    (test / bad_name).write_text('unsafe')
    stage = tmp_path / 'stage'
    with pytest.raises(ValueError, match='충돌'):
        stage_merge(_audit(b'base\n'), main, test, stage)
    assert not stage.exists()


def test_windows_invalid_main_name_reported(tmp_path):
    main, _ = _roots(tmp_path)
    (main / 'AUX.log').write_bytes(b'bad')
    _, unsafe = _snapshot(main)
    assert any(item['reason'] == 'windows_reserved_name' for item in unsafe)


def test_original_history_folder_cannot_be_destination(tmp_path):
    main, test = _roots(tmp_path)
    old = tmp_path / 'historical'
    old.mkdir()
    (old / 'core.py').write_bytes(b'base\n')
    with pytest.raises(ValueError, match='과거 원본'):
        stage_merge(_audit(b'base\n'), main, test, old / 'stage', old)
    assert not (old / 'stage').exists()


def test_main_source_changed_during_copy_blocks_publish(tmp_path, monkeypatch):
    main, test = _roots(tmp_path)
    stage = tmp_path / 'stage'
    original_copy = stage_module.shutil.copyfile
    modified = False

    def concurrent_change(source, target):
        nonlocal modified
        result = original_copy(source, target)
        if not modified and Path(source) == main / 'core.py':
            (main / 'core.py').write_bytes(b'concurrent\n')
            modified = True
        return result

    monkeypatch.setattr(stage_module.shutil, 'copyfile', concurrent_change)
    with pytest.raises(ValueError, match='main 원본'):
        stage_merge(_audit(b'base\n'), main, test, stage)
    assert modified
    assert not stage.exists()
    assert (main / 'core.py').read_bytes() == b'concurrent\n'


def test_main_new_file_during_copy_blocks_publish(tmp_path, monkeypatch):
    main, test = _roots(tmp_path)
    stage = tmp_path / 'stage'
    original_copy = stage_module.shutil.copyfile

    def concurrent_new_file(source, target):
        result = original_copy(source, target)
        (main / 'new_main.txt').write_bytes(b'preserve me')
        return result

    monkeypatch.setattr(stage_module.shutil, 'copyfile', concurrent_new_file)
    with pytest.raises(ValueError, match='main 원본'):
        stage_merge(_audit(b'base\n'), main, test, stage)
    assert not stage.exists()
    assert (main / 'new_main.txt').read_bytes() == b'preserve me'
