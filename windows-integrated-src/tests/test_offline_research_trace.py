"""Stage54 partial: bounded offline links-to-saved-snapshots traversal."""
import socket
import sqlite3

import pytest

from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'trace.sqlite3')
    store.setup_owner('trace-owner', 'strong-trace-password-2026')
    return store


def snapshot(owner, url, links='', title='html'):
    return owner.add_offline_research(url, title, '<div>Text</div>' + links, 'html_snapshot')


def test_two_hop_local_chain_and_missing_url(owner):
    a = snapshot(owner, 'https://example.org/a', '<a href="/b">B</a><a href="/missing">No</a>')
    b = snapshot(owner, 'https://example.org/b', '<a href="/c">C</a>')
    c = owner.add_offline_research('https://example.org/c', 'leaf', 'Content')
    result = owner.trace_offline_research_references(a)
    assert [n['id'] for n in result['nodes']] == [a, b, c]
    assert [(e['from_id'], e['status']) for e in result['links']] == [
        (a, 'one'), (a, 'missing'), (b, 'one')]
    assert result['source_authenticity_verified'] is False
    assert result['network_accessed'] is False
    assert result['truncated'] is False


def test_depth_limit(owner):
    a = snapshot(owner, 'https://example.org/a', '<a href="/b">B</a>')
    b = snapshot(owner, 'https://example.org/b', '<a href="/c">C</a>')
    c = snapshot(owner, 'https://example.org/c', '<a href="/d">D</a>')
    d = snapshot(owner, 'https://example.org/d')
    assert [n['id'] for n in owner.trace_offline_research_references(a, 1)['nodes']] == [a,b]
    assert [n['id'] for n in owner.trace_offline_research_references(a, 3)['nodes']] == [a,b,c,d]


def test_multiple_snapshots_with_same_claimed_url_are_ambiguous(owner):
    a = snapshot(owner, 'https://example.org/a', '<a href="/b">B</a>')
    b1 = owner.add_offline_research('https://example.org/b','b1','first content')
    b2 = owner.add_offline_research('https://example.org/b','b2','second content')
    result = owner.trace_offline_research_references(a)
    assert result['links'][0]['status'] == 'multiple'
    assert result['links'][0]['candidate_ids'] == [b1,b2]
    assert {n['id'] for n in result['nodes']} == {a,b1,b2}


def test_cycle_is_safe_and_stable(owner):
    a = snapshot(owner, 'https://example.org/a', '<a href="/b">B</a>')
    b = snapshot(owner, 'https://example.org/b', '<a href="/a">A</a>')
    result = owner.trace_offline_research_references(a, 3)
    assert len(result['nodes']) == 2
    assert len(result['links']) == 2
    assert result['links'][1]['candidate_ids'] == [a]


def test_archived_capture_is_preserved(owner):
    a = snapshot(owner, 'https://example.org/a', '<a href="/b">B</a>')
    b = snapshot(owner, 'https://example.org/b')
    owner.archive_offline_research(b)
    result = owner.trace_offline_research_references(a)
    assert result['nodes'][1]['id'] == b
    assert result['nodes'][1]['archived'] is True


def test_legacy_snapshots_not_fabricated(owner):
    a = owner.add_offline_research('https://example.org/a', 'plain',
                                   '<a href="/b">B</a>', 'manual_text')
    owner.add_offline_research('https://example.org/b', 'other', 'A')
    assert owner.trace_offline_research_references(a)['links'] == []


def test_invalid_depth_and_id(owner):
    for value in (0,-1,'1',None,True,1.5):
        with pytest.raises(ValueError):
            owner.trace_offline_research_references(value)
    a = snapshot(owner, 'https://example.org/a')
    for value in (-1,0,4,'2',None,True,2.4):
        with pytest.raises(ValueError):
            owner.trace_offline_research_references(a,value)
    with pytest.raises(ValueError):
        owner.trace_offline_research_references(999)


def test_permission_denied_before_lookup(owner):
    owner.logout()
    with pytest.raises(AuthenticationError):
        owner.trace_offline_research_references(1)


def test_persists_after_restart(owner):
    a = snapshot(owner,'https://example.org/a','<a href="/b">B</a>')
    snapshot(owner,'https://example.org/b')
    before = owner.trace_offline_research_references(a)
    owner.logout()
    restored = LocalStore(owner.path)
    restored.login('trace-owner','strong-trace-password-2026')
    assert restored.trace_offline_research_references(a) == before


def test_read_only_no_database_mutation(owner):
    a = snapshot(owner,'https://example.org/a','<a href="/b">B</a>')
    snapshot(owner,'https://example.org/b')
    with sqlite3.connect(owner.path) as con:
        original = con.iterdump()
        dump_before = list(original)
    owner.trace_offline_research_references(a)
    with sqlite3.connect(owner.path) as con:
        assert list(con.iterdump()) == dump_before


def test_no_network(owner, monkeypatch):
    def prohibited(*args, **kwargs):
        raise AssertionError('network accessed')
    monkeypatch.setattr(socket.socket,'connect',prohibited)
    monkeypatch.setattr(socket.socket,'connect_ex',prohibited)
    monkeypatch.setattr(socket,'create_connection',prohibited)
    a = snapshot(owner,'https://example.org/a','<a href="https://external.example.org/b">B</a>')
    assert owner.trace_offline_research_references(a)['links'][0]['status'] == 'missing'


def test_node_limit_in_large_local_set(owner):
    links = ''.join(f'<a href="/p{i}">p{i}</a>' for i in range(60))
    a = snapshot(owner,'https://example.org/root',links)
    for i in range(60):
        owner.add_offline_research(f'https://example.org/p{i}',f'p{i}',f'unique body {i}')
    result = owner.trace_offline_research_references(a)
    assert len(result['nodes']) == 50
    assert result['truncated'] is True
    assert result['network_accessed'] is False
