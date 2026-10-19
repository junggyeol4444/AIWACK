"""Stage63 manual offline demand/competition source-link and audit regression."""
import hashlib
import socket
import sqlite3
from unittest.mock import patch

import pytest

from desktop.storage import LocalStore


BODY = '관찰 메모: 문의가 늘었다는 주장이 있다. 경쟁사 A의 가격이 낮다는 주장도 있다.'
QUOTE = '문의가 늘었다는 주장이 있다.'
COMPETITION = '경쟁사 A의 가격이 낮다는 주장도 있다.'


def setup(tmp_path):
    s = LocalStore(tmp_path / 'owner.sqlite3')
    s.setup_owner('owner63', 'stage63-long-password')
    candidate = s.generate_business_candidates('지역 고객', '반복 업무', 1)['created_ids'][0]
    capture = s.add_offline_research('https://example.org/claimed', '직접 입력한 주장', BODY)
    return s, candidate, capture


def test_link_is_local_and_not_market_validation(tmp_path):
    s, cid, rid = setup(tmp_path)
    ident = s.link_market_evidence(cid, rid, 'demand', 'supports', QUOTE, '원문 인용 여부만 확인')
    rows = s.market_evidence(cid)
    assert len(rows) == 1
    assert rows[0]['id'] == ident and rows[0]['capture_id'] == rid
    assert rows[0]['source_verified'] is False
    assert rows[0]['source_url'] == 'https://example.org/claimed'
    result = s.market_evidence_summary(cid)
    assert result['market_demand_verified'] is False
    assert result['competition_verified'] is False
    assert result['source_authenticity_verified'] is False
    assert result['independent_sources_verified'] is False
    assert result['external_actions_executed'] is False
    assert result['categories']['demand']['reviewed_links'] == 0
    assert result['categories']['competition']['missing_local_material'] is True
    assert [r['action'] for r in s.market_evidence_events(ident)] == ['linked']


def test_review_is_only_a_manual_note_not_verification(tmp_path):
    s, cid, rid = setup(tmp_path)
    d = s.link_market_evidence(cid, rid, 'demand', 'supports', QUOTE, '수요 주장')
    c = s.link_market_evidence(cid, rid, 'competition', 'challenges', COMPETITION, '경쟁 주장')
    assert s.review_market_evidence(d, 'noted')['source_verified'] is False
    s.review_market_evidence(c, 'noted')
    report = s.market_evidence_summary(cid)
    assert report['categories']['demand']['local_capture_count'] == 1
    assert report['categories']['competition']['local_capture_count'] == 1
    assert report['market_demand_verified'] is False
    assert report['categories']['competition']['challenging_claims'] == 1
    s.review_market_evidence(c, 'excluded')
    assert s.market_evidence_summary(cid)['categories']['competition']['missing_local_material'] is True
    assert [x['action'] for x in s.market_evidence_events(c)] == [
        'review_changed', 'review_changed', 'linked']
    with pytest.raises(ValueError):
        s.review_market_evidence(c, 'excluded')


@pytest.mark.parametrize('kind,stance,excerpt,note', [
    ('other','supports',QUOTE,'memo'), ('demand','false',QUOTE,'memo'),
    ('demand','supports','원문에 없는 문장입니다.','memo'),
    ('demand','supports','짧음','memo'),
    ('demand','supports',QUOTE,''),
    ('demand','supports',QUOTE,'password=12345'),
    ('demand','supports',QUOTE,'\nnewline'),
    ([], 'supports', QUOTE, 'memo'),
    ('demand', [], QUOTE, 'memo'),
    ('demand','supports',QUOTE,'x'*301),
])
def test_invalid_inputs_never_insert(tmp_path, kind, stance, excerpt, note):
    s, cid, rid = setup(tmp_path)
    with pytest.raises(ValueError):
        s.link_market_evidence(cid, rid, kind, stance, excerpt, note)
    assert s.market_evidence(cid) == []


def test_unknown_ids_and_duplicate(tmp_path):
    s, cid, rid = setup(tmp_path)
    for bad in (0, -1, True, '1', 99_999):
        with pytest.raises(ValueError):
            s.link_market_evidence(bad, rid, 'demand', 'context', QUOTE, '메모')
        with pytest.raises(ValueError):
            s.link_market_evidence(cid, bad, 'demand', 'context', QUOTE, '메모')
    link = s.link_market_evidence(cid, rid, 'demand', 'context', QUOTE, '메모')
    with pytest.raises(ValueError, match='동일'):
        s.link_market_evidence(cid, rid, 'demand', 'context', QUOTE, '메모2')
    for bad in (0, -1, True, '1', 999):
        with pytest.raises(ValueError):
            s.review_market_evidence(bad, 'noted')
        with pytest.raises(ValueError):
            s.market_evidence_events(bad)
    with pytest.raises(ValueError):
        s.review_market_evidence(link, 'validated')
    for bad in (0, 101, True):
        with pytest.raises(ValueError):
            s.market_evidence(cid, bad)


def test_owner_access_logout_and_persistence(tmp_path):
    s, cid, rid = setup(tmp_path)
    ident = s.link_market_evidence(cid, rid, 'demand', 'context', QUOTE, '메모')
    s.logout()
    for action in [lambda: s.link_market_evidence(cid,rid,'demand','context',QUOTE,'메모'),
                   lambda: s.market_evidence(cid),
                   lambda: s.market_evidence_summary(cid),
                   lambda: s.review_market_evidence(ident,'noted'),
                   lambda: s.market_evidence_events(ident)]:
        with pytest.raises(PermissionError):
            action()
    reopened = LocalStore(s.path)
    reopened.login('owner63', 'stage63-long-password')
    assert reopened.market_evidence(cid)[0]['id'] == ident
    assert reopened.market_evidence_summary(cid)['source_authenticity_verified'] is False


def test_immutable_links_and_events_and_tamper_detection(tmp_path):
    s, cid, rid = setup(tmp_path)
    ident = s.link_market_evidence(cid, rid, 'demand', 'context', QUOTE, '메모')
    with s._connect() as con:
        for statement in ["DELETE FROM market_evidence_links",
                          "UPDATE market_evidence_links SET excerpt='fake'",
                          "DELETE FROM market_evidence_events",
                          "UPDATE market_evidence_events SET detail='{}'"]:
            with pytest.raises(sqlite3.DatabaseError):
                con.execute(statement)
        con.execute('DROP TRIGGER market_evidence_events_no_update')
        con.execute('UPDATE market_evidence_events SET detail=? WHERE link_id=?', ('{}', ident))
    with pytest.raises(ValueError, match='감사 이벤트'):
        s.market_evidence(cid)


def test_capture_hash_tamper_detected(tmp_path):
    s, cid, rid = setup(tmp_path)
    s.link_market_evidence(cid, rid, 'demand', 'context', QUOTE, '메모')
    with s._connect() as con:
        con.execute('DROP TRIGGER offline_research_immutable')
        con.execute('UPDATE offline_research_captures SET body=? WHERE id=?', ('바뀐 자료', rid))
    with pytest.raises(ValueError, match='무결성'):
        s.market_evidence(cid)


def test_no_network_and_no_auto_candidate_promotion(tmp_path):
    s, cid, rid = setup(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('No socket or DNS allowed')
    with patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        ident = s.link_market_evidence(cid, rid, 'competition', 'challenges', COMPETITION, '주장')
        s.review_market_evidence(ident, 'noted')
        assert s.market_evidence_summary(cid)['competition_verified'] is False
    assert s.business_candidates()[0]['state'] == 'draft'
    assert s.list_businesses() == []


def test_atomic_failure_rollback(tmp_path):
    s, cid, rid = setup(tmp_path)
    with s._connect() as con:
        con.execute('''CREATE TRIGGER fail_market_event BEFORE INSERT ON market_evidence_events
          BEGIN SELECT RAISE(ABORT,'forced'); END''')
    with pytest.raises(sqlite3.DatabaseError):
        s.link_market_evidence(cid, rid, 'demand', 'supports', QUOTE, '메모')
    assert s.market_evidence(cid) == []


def test_no_local_sources_does_not_invent_research(tmp_path):
    s = LocalStore(tmp_path / 'blank.sqlite3')
    s.setup_owner('owner63', 'stage63-long-password')
    cid = s.generate_business_candidates('고객', '문제', 1)['created_ids'][0]
    assert s.market_evidence(cid) == []
    summary = s.market_evidence_summary(cid)
    assert all(x['missing_local_material'] for x in summary['categories'].values())
    assert summary['market_demand_verified'] is False
