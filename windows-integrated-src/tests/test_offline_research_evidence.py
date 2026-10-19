"""Offline evidence quotes: never infer source authenticity or fetch a URL."""
from pathlib import Path
import json
import socket
import sqlite3

import pytest

from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'owner.sqlite3')
    store.setup_owner('evidence-owner', 'evidence-owner-password-2026')
    return store


def capture(store, url, body, title='test'):
    return store.add_offline_research(url, title, body)


def test_multiple_sources_cited_and_unverified(owner):
    a = capture(owner, 'https://example.org/a', 'Section one\nKey insight alpha')
    b = capture(owner, 'https://example.org/b', 'Beta\nSecond KEY INSIGHT is here')
    report = owner.local_research_evidence_report('key insight')
    assert [x['capture_id'] for x in report['hits']] == [b, a]
    assert report['hits'][0]['excerpts'][0]['line'] == 2
    assert report['hits'][1]['excerpts'][0]['line'] == 2
    assert report['source_authenticity_verified'] is False
    assert report['network_accessed'] is False
    assert '온라인 출처' in report['report_text'] or '출처·내용 진위' in report['report_text']
    for hit in report['hits']:
        assert hit['local_content_hash_matches']
        assert hit['source_verification'] == 'unverified'
        assert hit['content_sha256'] in report['report_text']
        assert f'#{hit["capture_id"]}' in report['report_text']


def test_body_only_no_title_url_false_matches(owner):
    capture(owner, 'https://keyword.example.org/foo', 'body with nothing', 'keyword title')
    assert owner.local_research_evidence_report('keyword')['hits'] == []


def test_archival_and_two_quotes_per_capture(owner):
    first = capture(owner, 'https://example.org/a', 'first term\nsecond term\nthird term')
    owner.archive_offline_research(first)
    assert owner.local_research_evidence_report('term')['hits'] == []
    report = owner.local_research_evidence_report('term', include_archived=True)
    assert report['hits'][0]['archived'] is True
    assert [x['line'] for x in report['hits'][0]['excerpts']] == [1,2]


def test_duplicate_url_stays_separate(owner):
    a = capture(owner, 'https://example.org/a', 'fruit orange')
    b = capture(owner, 'https://example.org/a', 'fruit melon')
    assert [h['capture_id'] for h in owner.local_research_evidence_report('fruit')['hits']] == [b,a]


def test_control_input_and_limit_errors(owner):
    invalid = ('', '  ', 'x'*81, 'line\nnext', 'bad\x00query', None, 10)
    for query in invalid:
        with pytest.raises(ValueError):
            owner.local_research_evidence_report(query)
    for limit in (0,21,'4',True,-1):
        with pytest.raises(ValueError):
            owner.local_research_evidence_report('x',limit=limit)
    for archived in ('yes',1,None):
        with pytest.raises(ValueError):
            owner.local_research_evidence_report('x',include_archived=archived)


def test_unicode_literal_percent_underscore(owner):
    a = capture(owner,'https://example.org/a','한국어 테스트 100% complete _data')
    assert owner.local_research_evidence_report('한국어')['hits'][0]['capture_id'] == a
    assert owner.local_research_evidence_report('100%')['hits'][0]['capture_id'] == a
    assert owner.local_research_evidence_report('_data')['hits'][0]['capture_id'] == a
    assert owner.local_research_evidence_report('not_here')['hits'] == []


def test_long_quote_is_truncated(owner):
    capture(owner, 'https://example.org/a', 'x'*1500 + 'needle'+'y'*1500)
    quote = owner.local_research_evidence_report('needle')['hits'][0]['excerpts'][0]['text']
    assert 'needle' in quote
    assert len(quote) < 200
    assert quote.startswith('…') and quote.endswith('…')


def test_limit_is_bounded(owner):
    for i in range(27):
        capture(owner,f'https://example.org/{i}','topic '+str(i))
    report = owner.local_research_evidence_report('topic',limit=8)
    assert len(report['hits']) == 8
    assert report['truncated']


def test_auth_and_restart(owner):
    first = capture(owner,'https://example.org/a','persistent evidence')
    before = owner.local_research_evidence_report('persistent')
    owner.logout()
    with pytest.raises(AuthenticationError):
        owner.local_research_evidence_report('persistent')
    restored=LocalStore(owner.path)
    restored.login('evidence-owner','evidence-owner-password-2026')
    after=restored.local_research_evidence_report('persistent')
    assert after == before
    assert after['hits'][0]['capture_id'] == first


def test_read_only_does_not_change_db(owner):
    capture(owner,'https://example.org/a','read only')
    with sqlite3.connect(owner.path) as con:
        before=list(con.iterdump())
    owner.local_research_evidence_report('read')
    with sqlite3.connect(owner.path) as con:
        assert list(con.iterdump()) == before


def test_network_forbidden(owner,monkeypatch):
    def deny(*args,**kwargs):
        raise AssertionError('network access forbidden')
    monkeypatch.setattr(socket.socket,'connect',deny)
    monkeypatch.setattr(socket.socket,'connect_ex',deny)
    monkeypatch.setattr(socket,'create_connection',deny)
    capture(owner, 'https://never-contact.example.org/a', 'offline needle')
    assert owner.local_research_evidence_report('needle')['hits']
