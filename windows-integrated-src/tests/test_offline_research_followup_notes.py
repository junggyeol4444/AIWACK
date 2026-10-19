"""Stage54 append-only offline URL triage (never remote verification)."""
import socket
import sqlite3

import pytest

from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'triage.sqlite3')
    store.setup_owner('owner-triage', 'owner-password-2026')
    store.add_offline_research('https://example.org/source', 'HTML snapshot',
        '<p>Saved offline</p><a href="/next">Next</a>', 'html_snapshot')
    return store


URL = 'https://example.org/next'


def test_new_annotations_in_queue_do_not_change_status(owner):
    before = owner.offline_research_followup_queue()
    assert before['items'][0]['manual_review'] is None
    ident = owner.record_offline_research_followup_note(URL, 'noted', 'Check with owner later')
    assert ident > 0
    after = owner.offline_research_followup_queue()
    assert after['status_counts'] == before['status_counts']
    assert after['items'][0]['status'] == 'unregistered'
    assert after['items'][0]['manual_review']['action'] == 'noted'
    assert after['items'][0]['manual_review']['note'] == 'Check with owner later'
    assert after['source_authenticity_verified'] is False
    assert after['network_accessed'] is False


def test_latest_note_and_history_order(owner):
    first = owner.record_offline_research_followup_note(URL, 'deferred', 'Wait for local copy')
    second = owner.record_offline_research_followup_note(URL, 'reopen', 'Resume local review')
    history = owner.offline_research_followup_history(URL)
    assert [row['id'] for row in history['items']] == [second, first]
    assert history['truncated'] is False
    assert history['source_authenticity_verified'] is False
    assert owner.offline_research_followup_queue()['items'][0]['manual_review']['action'] == 'reopen'


def test_restart_retains_annotations(owner):
    owner.record_offline_research_followup_note(URL, 'noted', 'Persist this')
    path = owner.path
    owner.logout()
    reopened = LocalStore(path)
    reopened.login('owner-triage', 'owner-password-2026')
    assert reopened.offline_research_followup_history(URL)['items'][0]['note'] == 'Persist this'


def test_append_only_triggers(owner):
    ident = owner.record_offline_research_followup_note(URL, 'noted', 'Original')
    with sqlite3.connect(owner.path) as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('UPDATE offline_research_followup_notes SET note=? WHERE id=?', ('changed', ident))
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM offline_research_followup_notes WHERE id=?', (ident,))
    assert owner.offline_research_followup_history(URL)['items'][0]['note'] == 'Original'


@pytest.mark.parametrize('action', ['', 'verified', 'fetched', 'done', None, 1, True])
def test_unapproved_actions_rejected(owner, action):
    with pytest.raises(ValueError):
        owner.record_offline_research_followup_note(URL, action, 'a note')


@pytest.mark.parametrize('note', ['', ' ', 'x' * 501, '\x00hidden', '\rfoo', None, 1])
def test_bad_notes_rejected(owner, note):
    with pytest.raises(ValueError):
        owner.record_offline_research_followup_note(URL, 'noted', note)


def test_unknown_or_non_web_url_rejected(owner):
    for url in ['https://example.org/unknown', 'file:///tmp/test', 'javascript:alert(1)',
                'http://localhost/private']:
        with pytest.raises(ValueError):
            owner.record_offline_research_followup_note(url, 'noted', 'Never write')
    with sqlite3.connect(owner.path) as con:
        assert con.execute('SELECT COUNT(*) FROM offline_research_followup_notes').fetchone()[0] == 0


def test_owner_auth_required(owner):
    owner.logout()
    with pytest.raises(AuthenticationError):
        owner.record_offline_research_followup_note(URL, 'noted', 'Blocked')
    with pytest.raises(AuthenticationError):
        owner.offline_research_followup_history(URL)


def test_bounded_history(owner):
    for index in range(22):
        owner.record_offline_research_followup_note(URL, 'noted', f'Note {index}')
    report = owner.offline_research_followup_history(URL)
    assert len(report['items']) == 20 and report['truncated']
    assert report['items'][0]['note'] == 'Note 21'
    assert len(owner.offline_research_followup_history(URL, limit=2)['items']) == 2
    for limit in [0, 21, True, '10']:
        with pytest.raises(ValueError):
            owner.offline_research_followup_history(URL, limit=limit)


def test_read_only_history_and_queue(owner):
    owner.record_offline_research_followup_note(URL, 'noted', 'Offline only')
    with sqlite3.connect(owner.path) as con:
        before = list(con.iterdump())
    owner.offline_research_followup_history(URL)
    owner.offline_research_followup_queue()
    with sqlite3.connect(owner.path) as con:
        assert list(con.iterdump()) == before


def test_network_calls_blocked(owner, monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('Network was used')
    monkeypatch.setattr(socket.socket, 'connect', blocked)
    monkeypatch.setattr(socket.socket, 'connect_ex', blocked)
    monkeypatch.setattr(socket, 'create_connection', blocked)
    owner.record_offline_research_followup_note(URL, 'noted', 'No network')
    assert owner.offline_research_followup_history(URL)['items']
    assert owner.offline_research_followup_queue()['items']


def test_schema_migration_does_not_change_captures(owner):
    with sqlite3.connect(owner.path) as con:
        before = con.execute('SELECT * FROM offline_research_captures').fetchall()
        from desktop.research_captures import initialize
        initialize(con)
        initialize(con)
        assert con.execute('SELECT * FROM offline_research_captures').fetchall() == before
