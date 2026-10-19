"""Stage54 partial: owner-approved passive URL warning JSON and local recheck."""
import hashlib
import json
import socket
import sqlite3

import pytest

from desktop.research_followup_exports import _canonical
from desktop.research_preflight_exports import (
    build_preflight_export_report, encode_preflight_export, verify_preflight_export,
)
from desktop.storage import AuthenticationError, LocalStore


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'owner.sqlite3')
    store.setup_owner('preflight-export-owner', 'long-password-2026')
    return store


def capture(owner, links):
    return owner.add_offline_research(
        'https://source.example/article', 'Offline snapshot',
        '<p>Offline only</p>' + ''.join(f'<a href="{link}">link</a>' for link in links),
        'html_snapshot')


def test_roundtrip_full_report_over_gui_limit(owner, tmp_path):
    urls = [f'https://127.0.0.{n}/a' for n in range(1, 84)]
    capture(owner, urls + ['https://ordinary.example/a'])
    output = tmp_path / 'warnings.json'
    with sqlite3.connect(owner.path) as con:
        before = list(con.iterdump())
    assert owner.export_offline_research_url_preflight(output) == output
    report = verify_preflight_export(output.read_bytes())
    assert report['warning_url_count'] == 83
    assert len(report['items']) == 83
    assert report['filtered_url_count'] == 84
    assert report['warning_counts'] == {'ip_literal': 83, 'non_global_ip_literal': 83}
    assert not any(report[k] for k in (
        'dns_checked', 'network_accessed', 'safe_to_fetch_verified',
        'source_authenticity_verified'))
    check = owner.inspect_offline_research_url_preflight_export(output)
    assert check['checksum_matches'] and check['local_report_matches']
    assert check['added_warning_url_count'] == check['missing_warning_url_count'] == 0
    with sqlite3.connect(owner.path) as con:
        assert list(con.iterdump()) == before


def test_added_missing_and_status_changed(owner, tmp_path):
    capture(owner, ['https://127.0.0.1/a', 'https://127.0.0.2/b'])
    output = tmp_path / 'warnings.json'
    owner.export_offline_research_url_preflight(output)
    # Same URL gains a local active copy; status changes without URL changing.
    owner.add_offline_research('https://127.0.0.1/a', 'Local copy', 'text', 'manual_text')
    capture(owner, ['https://machine.local/new'])
    diff = owner.inspect_offline_research_url_preflight_export(output)
    assert not diff['local_report_matches']
    assert diff['added_urls_preview'] == ['https://machine.local/new']
    assert diff['changed_urls_preview'] == ['https://127.0.0.1/a']
    assert diff['missing_warning_url_count'] == 0


def test_filter_and_archive_scope(owner, tmp_path):
    ident = capture(owner, ['https://machine.local/keep', 'https://127.0.0.1/later'])
    owner.record_offline_research_followup_note('https://127.0.0.1/later', 'deferred', 'later')
    pending = tmp_path / 'pending.json'
    owner.export_offline_research_url_preflight(pending, review_filter='pending')
    report = verify_preflight_export(pending.read_bytes())
    assert report['warning_url_count'] == 1
    assert report['items'][0]['linked_url'] == 'https://machine.local/keep'
    assert owner.inspect_offline_research_url_preflight_export(pending)['local_report_matches']
    owner.archive_offline_research(ident)
    diff = owner.inspect_offline_research_url_preflight_export(pending)
    assert diff['missing_urls_preview'] == ['https://machine.local/keep']
    all_file = tmp_path / 'archived.json'
    owner.export_offline_research_url_preflight(all_file, include_archived=True)
    assert verify_preflight_export(all_file.read_bytes())['warning_url_count'] == 2


def test_recheck_uses_saved_filter(owner, tmp_path):
    capture(owner, ['https://machine.local/keep', 'https://127.0.0.1/later'])
    owner.record_offline_research_followup_note('https://127.0.0.1/later', 'deferred', 'later')
    output = tmp_path / 'deferred.json'
    owner.export_offline_research_url_preflight(output, review_filter='deferred')
    owner.record_offline_research_followup_note('https://127.0.0.1/later', 'reopen', 'again')
    diff = owner.inspect_offline_research_url_preflight_export(output)
    assert diff['missing_warning_url_count'] == 1
    assert diff['review_filter'] == 'deferred'


def test_tampering_checksum_rejected(owner, tmp_path):
    capture(owner, ['https://127.0.0.1/secret'])
    output = tmp_path / 'report.json'
    owner.export_offline_research_url_preflight(output)
    envelope = json.loads(output.read_text(encoding='utf-8'))
    envelope['report']['items'][0]['status'] = 'one_active'
    output.write_text(json.dumps(envelope), encoding='utf-8')
    with pytest.raises(ValueError, match='체크섬'):
        owner.inspect_offline_research_url_preflight_export(output)


@pytest.mark.parametrize('field,value', [
    ('warning_url_count', 99),
    ('warning_counts', {'ip_literal': 999}),
    ('network_accessed', True),
    ('safe_to_fetch_verified', True),
    ('review_filter', 'invalid'),
])
def test_rechecks_structure_even_if_checksum_recomputed(owner, tmp_path, field, value):
    capture(owner, ['https://127.0.0.1/a'])
    output = tmp_path / 'report.json'
    owner.export_offline_research_url_preflight(output)
    envelope = json.loads(output.read_text(encoding='utf-8'))
    envelope['report'][field] = value
    envelope['report_sha256'] = hashlib.sha256(_canonical(envelope['report'])).hexdigest()
    with pytest.raises(ValueError):
        verify_preflight_export(json.dumps(envelope).encode())


def test_warning_code_forgery_rejected_with_new_checksum(owner, tmp_path):
    capture(owner, ['https://127.0.0.1/a'])
    output = tmp_path / 'report.json'
    owner.export_offline_research_url_preflight(output)
    envelope = json.loads(output.read_text(encoding='utf-8'))
    envelope['report']['items'][0]['warning_codes'] = ['ip_literal']
    envelope['report_sha256'] = hashlib.sha256(_canonical(envelope['report'])).hexdigest()
    with pytest.raises(ValueError, match='경고 코드'):
        verify_preflight_export(json.dumps(envelope).encode())


def test_invalid_json_and_format(owner, tmp_path):
    output = tmp_path / 'bad.json'
    output.write_bytes(b'not json')
    with pytest.raises(ValueError):
        owner.inspect_offline_research_url_preflight_export(output)
    with pytest.raises(ValueError):
        verify_preflight_export(b'{}')
    with pytest.raises(ValueError):
        verify_preflight_export(b'x' * 12_000_001)


def test_exclusive_no_overwrite(owner, tmp_path):
    output = tmp_path / 'existing.json'
    output.write_bytes(b'preserve')
    with pytest.raises(FileExistsError):
        owner.export_offline_research_url_preflight(output)
    assert output.read_bytes() == b'preserve'


@pytest.mark.parametrize('path', ['relative.json', '//remote/share/file.json', '\\\\host\\share\\file.json'])
def test_invalid_export_path(owner, path):
    with pytest.raises(ValueError):
        owner.export_offline_research_url_preflight(path)


def test_symlink_input_rejected(owner, tmp_path):
    output = tmp_path / 'warnings.json'
    owner.export_offline_research_url_preflight(output)
    link = tmp_path / 'linked.json'
    link.symlink_to(output)
    with pytest.raises(ValueError):
        owner.inspect_offline_research_url_preflight_export(link)


def test_auth_before_paths(owner, tmp_path):
    owner.logout()
    with pytest.raises(AuthenticationError):
        owner.export_offline_research_url_preflight(tmp_path / 'out.json')
    with pytest.raises(AuthenticationError):
        owner.inspect_offline_research_url_preflight_export(tmp_path / 'missing.json')


def test_empty_report(owner, tmp_path):
    output = tmp_path / 'empty.json'
    owner.export_offline_research_url_preflight(output)
    assert verify_preflight_export(output.read_bytes())['items'] == []
    assert owner.inspect_offline_research_url_preflight_export(output)['local_report_matches']


def test_no_socket_and_relogin(owner, tmp_path, monkeypatch):
    capture(owner, ['https://machine.local/a'])
    output = tmp_path / 'warnings.json'
    def deny(*args, **kwargs):
        raise AssertionError('No network allowed')
    for attr in ('connect', 'connect_ex', 'sendto', 'sendall'):
        monkeypatch.setattr(socket.socket, attr, deny)
    monkeypatch.setattr(socket, 'getaddrinfo', deny)
    owner.export_offline_research_url_preflight(output)
    owner.logout()
    again = LocalStore(owner.path)
    again.login('preflight-export-owner', 'long-password-2026')
    assert again.inspect_offline_research_url_preflight_export(output)['local_report_matches']


def test_encode_validator_refuses_untrusted_report(owner):
    with owner._connect() as con:
        report = build_preflight_export_report(con)
    assert verify_preflight_export(encode_preflight_export(report)) == report
    report['warning_url_count'] = True
    with pytest.raises(ValueError):
        encode_preflight_export(report)
