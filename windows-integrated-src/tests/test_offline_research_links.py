"""Stage54 continuation: passive HTML hyperlinks, no online investigation."""
import json
import socket
import sqlite3

import pytest

from desktop.storage import LocalStore, AuthenticationError
from desktop.research_captures import extract_offline_links, initialize


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'links.sqlite3')
    store.setup_owner('owner-links', 'owner-links-strong-password')
    return store


def test_link_extraction_relative_absolute_and_unsafe(owner):
    html = '''<html><head><base href="https://attacker.example/"/></head><body>
      <a href="/guide#frag">Guide</a><a href="/guide#again">same</a>
      <a href="next?q=1">next</a><a href="https://other.example.org/p">external</a>
      <a href="javascript:alert(1)">unsafe</a><a href="data:text/html,evil">unsafe</a>
      <a href="mailto:x@example.org">mail</a><a href="file:///etc/passwd">file</a>
      <a href="http://localhost/admin">local</a><a href="https://site.example.org/page">self</a>
      <script><a href="https://bad.example/"></script>
      <a href="http://another.example:444/bad">port</a>
    </body></html>'''
    capture = owner.add_offline_research('https://site.example.org/page', 'sample', html, 'html_snapshot')
    records = owner.list_offline_research_links(capture)
    assert [row['linked_url'] for row in records] == [
        'https://site.example.org/guide',
        'https://site.example.org/next?q=1',
        'https://other.example.org/p',
    ]
    assert [row['position'] for row in records] == [1, 2, 3]
    assert all(row['source_verification'] == 'unverified' for row in records)
    assert not any(row['has_local_copy'] for row in records)
    owner.add_offline_research('https://site.example.org/guide', 'guide', 'content')
    assert owner.list_offline_research_links(capture)[0]['has_local_copy'] == 1
    assert owner.audit_offline_research()['passed']
    assert owner.read_offline_research(capture)['body'].startswith('Guide')


def test_manual_text_never_extracted_even_if_looks_like_html(owner):
    capture = owner.add_offline_research('https://example.org/a', 'plain',
        '<a href="https://example.org/b">test</a>')
    assert owner.list_offline_research_links(capture) == []


def test_archive_and_restart_preserve_immutable_links(owner):
    capture = owner.add_offline_research('https://example.org/a', 'linked',
        '<a href="/b">B</a>', 'html_snapshot')
    original = owner.list_offline_research_links(capture)
    assert owner.archive_offline_research(capture)
    owner.logout()
    reloaded = LocalStore(owner.path)
    reloaded.login('owner-links', 'owner-links-strong-password')
    assert original == reloaded.list_offline_research_links(capture)
    with sqlite3.connect(owner.path) as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM offline_research_html_links WHERE capture_id=?', (capture,))
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('UPDATE offline_research_html_links SET linked_url=? WHERE capture_id=?',
                        ('https://changed.example/', capture))


def test_html_file_import_and_batch_import(owner, tmp_path):
    sample = tmp_path / 'one.html'
    sample.write_text('<div>Source</div><a href="/next">Next</a>', encoding='utf-8')
    capture = owner.import_offline_research_file('https://example.org/one', 'one', sample)
    assert owner.list_offline_research_links(capture)[0]['linked_url'] == 'https://example.org/next'
    other = tmp_path / 'two.html'
    other.write_text('<div>Other</div><a href="https://example.org/one">One</a>',encoding='utf-8')
    manifest = tmp_path / 'sources.json'
    manifest.write_text(json.dumps({'format':'aiwack-offline-research-bundle-v1', 'items': [
        {'file':'two.html','url':'https://example.org/two','title':'two'}]}),encoding='utf-8')
    capture2 = owner.import_offline_research_bundle(manifest)['capture_ids'][0]
    assert owner.list_offline_research_links(capture2)[0]['has_local_copy'] == 1
    assert owner.audit_offline_research()['passed']


def test_100_cap_and_order(owner):
    html = '<p>many</p>' + ''.join(f'<a href="/p{i}">x</a>' for i in range(130))
    capture = owner.add_offline_research('https://example.org/a', 'many', html, 'html_snapshot')
    links = owner.list_offline_research_links(capture)
    assert len(links) == 100
    assert links[-1]['linked_url'].endswith('/p99')


def test_old_captures_are_not_backfilled(tmp_path):
    db = tmp_path / 'legacy.db'
    con = sqlite3.connect(db)
    initialize(con)
    con.execute('INSERT INTO offline_research_captures '
                '(source_url,title,body,capture_kind,content_sha256) VALUES(?,?,?,?,?)',
                ('https://example.org/old','old','old text','html_snapshot','a'*64))
    con.commit()
    con.execute('DROP TABLE offline_research_html_links')
    con.commit()
    initialize(con)
    assert con.execute('SELECT count(*) FROM offline_research_html_links').fetchone()[0] == 0
    con.close()


@pytest.mark.parametrize('capture_id', [0,-1,'1',None,True])
def test_invalid_identifiers(owner, capture_id):
    with pytest.raises(ValueError):
        owner.list_offline_research_links(capture_id)


def test_missing_identifier(owner):
    with pytest.raises(ValueError):
        owner.list_offline_research_links(123456)


def test_permission_denied_before_lookup(owner):
    owner.logout()
    with pytest.raises(AuthenticationError):
        owner.list_offline_research_links(1)


def test_no_network(owner, monkeypatch):
    def no_network(*a,**kw):
        raise AssertionError('network accessed')
    monkeypatch.setattr(socket.socket,'connect',no_network)
    monkeypatch.setattr(socket.socket,'connect_ex',no_network)
    monkeypatch.setattr(socket,'create_connection',no_network)
    ident = owner.add_offline_research('https://example.org/one','x',
        '<a href="https://different.example.org/anything">Link</a>', 'html_snapshot')
    assert len(owner.list_offline_research_links(ident)) == 1


def test_detect_corrupted_link_position(owner):
    capture = owner.add_offline_research('https://example.org/start', 'x',
        '<a href="/a">a</a><a href="/b">b</a>', 'html_snapshot')
    with sqlite3.connect(owner.path) as con:
        con.execute('DROP TRIGGER offline_research_html_links_no_update')
        con.execute('UPDATE offline_research_html_links SET position=3 WHERE capture_id=? AND position=2',
                    (capture,))
    result = owner.audit_offline_research()
    assert result['passed'] is False
    assert any('링크 목록' in i['issue'] for i in result['issues'])


def test_plain_extraction_api_has_no_network():
    assert extract_offline_links('<a href="/here">Here</a>',
           'https://example.org/a') == ['https://example.org/here']
