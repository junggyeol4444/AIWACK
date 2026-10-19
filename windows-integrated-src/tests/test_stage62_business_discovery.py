"""Stage62 offline hypothesis generation, lifecycle, access and audit tests."""
import socket
import sqlite3
from unittest.mock import patch

import pytest

from desktop.storage import LocalStore


def owner(tmp_path):
    s = LocalStore(tmp_path / 'stage62.sqlite3')
    s.setup_owner('owner62', 'stage62-long-password')
    return s


def test_hypotheses_are_unverified_and_bounded(tmp_path):
    s = owner(tmp_path)
    result = s.generate_business_candidates('1인 창업자', '반복 업무 정리', 5)
    assert len(result['created_ids']) == 5
    assert result['verified_market_data'] is False
    assert result['external_actions_executed'] is False
    rows = s.business_candidates()
    assert len(rows) == 5
    assert all(row['state'] == 'draft' for row in rows)
    assert all(row['source_kind'] == 'owner_input_unverified' for row in rows)
    assert all('조사되지 않았음' in row['hypothesis'] for row in rows)
    assert len(s.business_candidate_runs()) == 1
    assert s.business_candidate_runs()[0]['proposed'] == 5


def test_repeated_inputs_are_deduplicated_even_with_spacing_case(tmp_path):
    s = owner(tmp_path)
    s.generate_business_candidates('SMB', 'Repetitive Tasks', 3)
    again = s.generate_business_candidates('  smb ', 'repetitive   tasks ', 3)
    assert again['created_ids'] == []
    assert again['skipped_duplicates'] == 3
    assert len(s.business_candidates()) == 3
    assert s.business_candidate_runs()[0]['proposed'] == 0
    assert s.business_candidate_runs()[0]['skipped'] == 3
    # New type can still add an additional idea with the same assumption.
    s.add_business_type('niche62', '신규 사업 유형')
    more = s.generate_business_candidates('SMB', 'Repetitive Tasks', 16)
    assert len(more['created_ids']) == 12
    assert more['skipped_duplicates'] == 3


def test_disabled_types_excluded_and_existing_candidates_preserved(tmp_path):
    s = owner(tmp_path)
    first = s.generate_business_candidates('고객', '문제', 2)
    s.disable_business_type(1)
    next_run = s.generate_business_candidates('고객', '문제', 2)
    assert len(next_run['created_ids']) == 1
    assert next_run['skipped_duplicates'] == 1
    assert len(s.business_candidates()) == 3
    assert first['created_ids'][0] in [r['id'] for r in s.business_candidates()]


def test_review_state_and_audit(tmp_path):
    s = owner(tmp_path)
    cid = s.generate_business_candidates('대상', '문제', 1)['created_ids'][0]
    assert s.set_business_candidate_state(cid, 'shortlisted')['external_actions_executed'] is False
    with pytest.raises(ValueError):
        s.set_business_candidate_state(cid, 'shortlisted')
    s.set_business_candidate_state(cid, 'rejected')
    s.set_business_candidate_state(cid, 'draft')
    assert [e['action'] for e in s.business_candidate_events(cid)] == [
        'state_changed', 'state_changed', 'state_changed', 'proposed']
    assert s.business_candidates('draft')[0]['id'] == cid
    assert s.business_candidates('shortlisted') == []


@pytest.mark.parametrize('audience,problem,max_candidates', [
    ('', 'problem', 1), ('person', '', 1), ('x'*121, 'problem', 1),
    ('person', 'x'*241, 1), ('person\nsecond', 'problem', 1),
    ('person', 'password=secret', 1), ('api_key:secret', 'problem', 1),
    ('person', 'problem', 0), ('person', 'problem', 21),
    ('person', 'problem', True), ('person', 'problem', '8'),
])
def test_rejects_invalid_input_without_writes(tmp_path, audience, problem, max_candidates):
    s = owner(tmp_path)
    with pytest.raises(ValueError):
        s.generate_business_candidates(audience, problem, max_candidates)
    assert s.business_candidates() == []
    assert s.business_candidate_runs() == []


def test_rejects_invalid_ids_and_filters(tmp_path):
    s = owner(tmp_path)
    cid = s.generate_business_candidates('a', 'b', 1)['created_ids'][0]
    for bad in (0, -1, True, '1', 1.0, 9999):
        with pytest.raises(ValueError):
            s.set_business_candidate_state(bad, 'rejected')
        with pytest.raises(ValueError):
            s.business_candidate_events(bad)
    for bad in ('unknown', '', 42, []):
        with pytest.raises(ValueError):
            s.business_candidates(bad)
    for bad in (0, True, 501):
        with pytest.raises(ValueError):
            s.business_candidates(limit=bad)
        with pytest.raises(ValueError):
            s.business_candidate_events(cid, bad)
        with pytest.raises(ValueError):
            s.business_candidate_runs(bad)


def test_owner_auth_and_persistence(tmp_path):
    s = owner(tmp_path)
    s.save_note('이전 기록 유지')
    cid = s.generate_business_candidates('a', 'b', 1)['created_ids'][0]
    s.logout()
    operations = [lambda: s.generate_business_candidates('x', 'y', 1),
                  lambda: s.business_candidates(), lambda: s.business_candidate_runs(),
                  lambda: s.set_business_candidate_state(cid, 'rejected'),
                  lambda: s.business_candidate_events(cid)]
    for operation in operations:
        with pytest.raises(PermissionError):
            operation()
    reopened = LocalStore(s.path)
    reopened.login('owner62', 'stage62-long-password')
    assert reopened.read_note() == '이전 기록 유지'
    assert reopened.business_candidates()[0]['id'] == cid
    assert reopened.business_candidate_events(cid)[0]['action'] == 'proposed'


def test_audit_append_only_and_detects_tampering(tmp_path):
    s = owner(tmp_path)
    cid = s.generate_business_candidates('a', 'b', 1)['created_ids'][0]
    with s._connect() as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('UPDATE opportunity_events SET detail=?', ('{}',))
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM opportunity_events')
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM opportunity_runs')
        con.execute('DROP TRIGGER opportunity_events_no_update')
        con.execute('UPDATE opportunity_events SET detail=? WHERE candidate_id=?', ('{}', cid))
    with pytest.raises(ValueError, match='무결성'):
        s.business_candidate_events(cid)


def test_no_network_or_business_execution(tmp_path):
    s = owner(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('network must not be accessed')
    with patch.object(socket, 'socket', side_effect=forbidden), patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        result = s.generate_business_candidates('개발자', '시간 부족', 4)
        s.set_business_candidate_state(result['created_ids'][0], 'shortlisted')
        assert s.business_candidate_events(result['created_ids'][0])
    assert s.list_businesses() == []  # no auto-created operational businesses


def test_failure_rolls_back_run_and_all_candidates(tmp_path):
    s = owner(tmp_path)
    # Hypothesis text must be fully retained, never silently truncated.
    with s._connect() as con:
        con.execute("UPDATE business_types SET title=? WHERE id=1", ('a'*100,))
    # Long valid fields can overflow the combined hypothesis: reject atomically.
    with pytest.raises(ValueError, match='너무 깁니다'):
        s.generate_business_candidates('x'*120, 'y'*240, 1)
    assert s.business_candidate_runs() == []
    assert len(s.generate_business_candidates('x', 'y', 1)['created_ids']) == 1
    # Trigger forced failure on second candidate to verify transaction rollback.
    with s._connect() as con:
        con.execute('''CREATE TRIGGER reject_second_candidate BEFORE INSERT ON opportunity_candidates
            WHEN NEW.type_id=2 BEGIN SELECT RAISE(ABORT,'forced failure'); END''')
    before = len(s.business_candidate_runs())
    with pytest.raises(sqlite3.DatabaseError):
        s.generate_business_candidates('new', 'new problem', 2)
    assert len(s.business_candidate_runs()) == before
    assert len(s.business_candidates()) == 1


def test_generation_without_active_types(tmp_path):
    s = owner(tmp_path)
    for row in s.business_types():
        s.disable_business_type(row['id'])
    with pytest.raises(ValueError, match='활성'):
        s.generate_business_candidates('a', 'b', 2)
    assert s.business_candidate_runs() == []
