"""원본 ZIP의 역사 증빙 단계에서 위험 파일을 실제로 보존하지 않는지 검증."""
import hashlib
import stat
import zipfile

import pytest

from validation.export_historical_version_evidence import export_historical_versions


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _audit(names):
    return {'coverage_confirmed': True, 'distinct_original_paths': len(names),
            'identical': [{'path': name, 'original_versions': [{'sha256': _sha(data)}]}
                          for name, data in names.items()],
            'changed': [], 'missing': [], 'version_conflicts': []}


def _zip(path, members):
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in members:
            archive.writestr(name, data)
    return path


def test_audit_windows_alias_conflict_is_rejected(tmp_path):
    source = _zip(tmp_path / 'source.zip', [('Foo.py', b'a')])
    with pytest.raises(ValueError, match='Windows 경로 충돌'):
        export_historical_versions(_audit({'Foo.py': b'a', 'foo.py': b'b'}),
                                   [source], tmp_path / 'evidence')
    assert not (tmp_path / 'evidence').exists()


@pytest.mark.parametrize('unsafe', ['../outside.py', 'CON.txt', 'unsafe\\name.py'])
def test_unknown_unsafe_zip_entries_are_rejected(tmp_path, unsafe):
    source = _zip(tmp_path / 'source.zip', [('good.py', b'ok'), (unsafe, b'bad')])
    with pytest.raises(ValueError, match='위험 경로'):
        export_historical_versions(_audit({'good.py': b'ok'}), [source], tmp_path / 'evidence')
    assert not (tmp_path / 'evidence').exists()


def test_symlink_entry_rejected_even_if_digest_matches(tmp_path):
    source = tmp_path / 'source.zip'
    with zipfile.ZipFile(source, 'w') as archive:
        entry = zipfile.ZipInfo('good.py')
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(entry, b'target')
    with pytest.raises(ValueError, match='링크'):
        export_historical_versions(_audit({'good.py': b'target'}),
                                   [source], tmp_path / 'evidence')
    assert not (tmp_path / 'evidence').exists()


def test_duplicate_zip_members_rejected(tmp_path):
    source = _zip(tmp_path / 'source.zip', [('good.py', b'ok'), ('good.py', b'ok')])
    with pytest.raises(ValueError, match='중복'):
        export_historical_versions(_audit({'good.py': b'ok'}),
                                   [source], tmp_path / 'evidence')


def test_windows_alias_collision_across_archives_rejected(tmp_path):
    first = _zip(tmp_path / 'one.zip', [('good.py', b'ok')])
    second = _zip(tmp_path / 'two.zip', [('GOOD.py', b'other')])
    with pytest.raises(ValueError, match='ZIP 간 Windows 경로 충돌'):
        export_historical_versions(_audit({'good.py': b'ok'}),
                                   [first, second], tmp_path / 'evidence')


def test_normal_multiversion_preserves_all_sha_and_sources(tmp_path):
    one, two = b'first', b'second'
    first = _zip(tmp_path / 'one.zip', [('good.py', one)])
    second = _zip(tmp_path / 'two.zip', [('good.py', two)])
    audit = _audit({'good.py': one})
    audit['identical'][0]['original_versions'].append({'sha256': _sha(two)})
    audit['version_conflicts'] = [{'path': 'good.py',
                                   'distinct_sha256': [_sha(one), _sha(two)]}]
    report = export_historical_versions(audit, [first, second], tmp_path / 'evidence')
    assert report['all_versions_recovered'] is True
    assert report['recovered_versions'] == 2
    assert (tmp_path / 'evidence' / 'versions' / '00001' / (_sha(one)+'.bin')).read_bytes() == one
    assert (tmp_path / 'evidence' / 'versions' / '00001' / (_sha(two)+'.bin')).read_bytes() == two
