"""역사 원본 ZIP의 위험 디렉터리·출력 경로를 실제 차단한다."""
import hashlib
import stat
import zipfile

import pytest
from validation.export_historical_version_evidence import export_historical_versions


def _audit():
    return {'coverage_confirmed': True, 'distinct_original_paths': 1,
            'identical': [{'path': 'safe/file.txt',
                           'original_versions': [{'sha256': hashlib.sha256(b'ok').hexdigest()}]}],
            'changed': [], 'missing': [], 'version_conflicts': []}


def _archive(tmp_path, directory):
    archive = tmp_path / 'history.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr(directory, b'')
        z.writestr('safe/file.txt', b'ok')
    return archive


@pytest.mark.parametrize('directory', ['../escape/', 'CON/', 'safe/../escape/', 'bad\\path/'])
def test_unsafe_directory_is_rejected(tmp_path, directory):
    archive = _archive(tmp_path, directory)
    with pytest.raises(ValueError, match='위험 경로'):
        export_historical_versions(_audit(), [archive], tmp_path / 'evidence')
    assert not (tmp_path / 'evidence').exists()


def test_directory_symlink_is_rejected(tmp_path):
    archive = tmp_path / 'history.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        info = zipfile.ZipInfo('safe/')
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(info, b'')
        z.writestr('safe/file.txt', b'ok')
    with pytest.raises(ValueError, match='링크'):
        export_historical_versions(_audit(), [archive], tmp_path / 'evidence')


def test_normal_directory_is_accepted(tmp_path):
    archive = _archive(tmp_path, 'safe/')
    result = export_historical_versions(_audit(), [archive], tmp_path / 'evidence')
    assert result['all_versions_recovered'] is True


def test_symlinked_destination_parent_is_rejected(tmp_path):
    archive = _archive(tmp_path, 'safe/')
    real = tmp_path / 'real'; real.mkdir()
    link = tmp_path / 'link'
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip('심볼릭 링크 사용 불가')
    with pytest.raises(ValueError, match='심볼릭 링크'):
        export_historical_versions(_audit(), [archive], link / 'evidence')
    assert not (real / 'evidence').exists()
