"""Stage61 generic local multi-business planning, safety, owner access and persistence."""
import sqlite3
import socket
from unittest.mock import patch

import pytest

from desktop.storage import LocalStore
from desktop.business_portfolio import EXAMPLE_TYPES, events


def owner(tmp_path):
    store = LocalStore(tmp_path / 'owner.sqlite3')
    store.setup_owner('owner61', 'stage61-owner-long-password')
    return store


def test_original_examples_are_templates_not_allowlist(tmp_path):
    s = owner(tmp_path)
    rows = s.business_types()
    assert len(rows) == len(EXAMPLE_TYPES) == 14
    assert {x['type_key'] for x in rows} == {x[0] for x in EXAMPLE_TYPES}
    custom = s.add_business_type('custom_niche', '새로운 합법적 사업', '새로운 범용 유형')
    assert custom > len(rows)
    assert s.create_business(custom, '첫 사업', '목표') > 0
    assert s.list_businesses()[0]['type_key'] == 'custom_niche'


def test_multiple_businesses_same_type_and_independent_states(tmp_path):
    s = owner(tmp_path)
    a = s.create_business(1, '첫 사업', '상품 기획', 15000)
    b = s.create_business(1, '두 번째 사업', '다른 목표', 9000)
    assert a != b
    s.set_business_state(a, 'active')
    s.set_business_state(a, 'paused')
    assert {x['id']: x['state'] for x in s.list_businesses()} == {a: 'paused', b: 'draft'}
    assert s.list_businesses()[0]['budget_krw'] == 9000
    assert len(s.business_events(a)) == 3


def test_state_machine_prevents_illegal_transitions(tmp_path):
    s = owner(tmp_path)
    a = s.create_business(1, '첫 사업', '목표')
    with pytest.raises(ValueError): s.set_business_state(a, 'paused')
    with pytest.raises(ValueError): s.set_business_state(a, 'draft')
    s.set_business_state(a, 'closed')
    for state in ('draft', 'active', 'paused', 'closed', 'invalid'):
        with pytest.raises(ValueError): s.set_business_state(a, state)
    assert s.list_businesses()[0]['state'] == 'closed'


@pytest.mark.parametrize('key', ['', 'ABCD', 'a-b', 'ab', 'x'*49, '가나다', 'foo bar'])
def test_invalid_type_key(tmp_path, key):
    s = owner(tmp_path)
    with pytest.raises(ValueError): s.add_business_type(key, 'name')


@pytest.mark.parametrize('name,goal,budget', [('', 'goal', 0), ('name', '', 0),
    ('x'*121, 'goal', 0), ('name', 'x'*501, 0), ('name', 'goal', -1),
    ('name', 'goal', True), ('name', 'goal', 1.5), ('name', 'goal', 10**13),
    ('password=secret', 'goal', 0), ('name', 'api_key:abc', 0),
    ('name\nline', 'goal', 0)])
def test_invalid_business_fields(tmp_path, name, goal, budget):
    s = owner(tmp_path)
    with pytest.raises(ValueError): s.create_business(1, name, goal, budget)


def test_disabled_type_preserves_history_and_prevents_new_business(tmp_path):
    s = owner(tmp_path)
    tid = s.add_business_type('my_type', '나만의 사업')
    bid = s.create_business(tid, '기존 사업', '목표')
    s.disable_business_type(tid)
    with pytest.raises(ValueError): s.create_business(tid, '새 사업', '목표')
    with pytest.raises(ValueError): s.disable_business_type(tid)
    assert s.list_businesses()[0]['id'] == bid
    assert any(e['action'] == 'type_disabled' for e in s.business_events())
    # Templates remain disabled after restart; no reseed re-enables them.
    s.logout()
    reopened = LocalStore(s.path)
    reopened.login('owner61', 'stage61-owner-long-password')
    assert next(t for t in reopened.business_types() if t['id'] == tid)['enabled'] == 0


def test_staff_references_and_many_to_many(tmp_path):
    s = owner(tmp_path)
    a = s.create_business(1, 'A', 'goal')
    b = s.create_business(2, 'B', 'goal')
    with pytest.raises(ValueError): s.create_business(1, 'C', 'goal', owner_employee_id=9999)
    with pytest.raises(ValueError): s.set_business_participant(a, 9999, True)
    with pytest.raises(ValueError): s.set_business_participant(a, None, True)
    # Use actual employee record from preexisting Stage14 schema.
    with s._connect() as con:
        cur = con.execute("INSERT INTO ai_employee_profiles(employee_key,display_name) VALUES ('staff61','Staff')")
        eid = cur.lastrowid
    s.set_business_participant(a, eid, True)
    s.set_business_participant(b, eid, True)
    assert len(s.business_participants(a)) == 1
    assert len(s.business_participants(b)) == 1
    with pytest.raises(ValueError): s.set_business_participant(a, eid, True)
    s.set_business_participant(a, eid, False)
    with pytest.raises(ValueError): s.set_business_participant(a, eid, False)
    assert len(s.business_participants(b)) == 1
    s.set_business_state(b, 'closed')
    with pytest.raises(ValueError): s.set_business_participant(b, eid, False)


def test_owner_employee_must_be_real(tmp_path):
    s = owner(tmp_path)
    with s._connect() as con:
        cur = con.execute("INSERT INTO ai_employee_profiles(employee_key,display_name) VALUES ('leader61','Leader')")
        eid = cur.lastrowid
    bid = s.create_business(1, 'Leader biz', 'goal', owner_employee_id=eid)
    assert s.list_businesses()[0]['owner_employee_id'] == eid
    assert s.list_businesses()[0]['participant_count'] == 1
    with pytest.raises(ValueError): s.set_business_participant(bid, eid, False)


def test_owner_auth_required_every_operation(tmp_path):
    s = owner(tmp_path)
    bid = s.create_business(1, 'A', 'goal')
    s.logout()
    calls = [lambda: s.business_types(), lambda: s.add_business_type('custom','title'),
             lambda: s.disable_business_type(1), lambda: s.create_business(1,'x','goal'),
             lambda: s.list_businesses(), lambda: s.set_business_state(bid,'active'),
             lambda: s.set_business_participant(bid,1,True),
             lambda: s.business_participants(bid), lambda: s.business_events()]
    for call in calls:
        with pytest.raises(PermissionError): call()


def test_append_only_events_detect_tampering(tmp_path):
    s = owner(tmp_path)
    bid = s.create_business(1, 'A', 'goal')
    with s._connect() as con:
        eid = con.execute('SELECT id FROM business_events WHERE business_id=?', (bid,)).fetchone()[0]
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('UPDATE business_events SET detail=? WHERE id=?', ('{}',eid))
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM business_events WHERE id=?', (eid,))
        con.execute('DROP TRIGGER business_events_no_update')
        con.execute('UPDATE business_events SET detail=? WHERE id=?', ('{}',eid))
    with pytest.raises(ValueError): s.business_events(bid)


def test_no_network_and_no_transactions(tmp_path):
    s = owner(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('external network forbidden')
    with patch.object(socket, 'socket', side_effect=forbidden), patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        tid = s.add_business_type('new_offline', '로컬 유형')
        bid = s.create_business(tid, '로컬 사업', '오프라인 목표', 100)
        result = s.set_business_state(bid, 'active')
        assert result['external_actions_executed'] is False
        assert s.business_events(bid)
        assert s.list_businesses()[0]['budget_krw'] == 100


def test_reopen_persists_all_and_other_tables(tmp_path):
    s = owner(tmp_path)
    s.save_note('기존 사용자 데이터 보존')
    tid = s.add_business_type('multi_type', '범용 유형')
    bid = s.create_business(tid, '새 사업', '목표')
    s.logout()
    again = LocalStore(s.path)
    again.login('owner61', 'stage61-owner-long-password')
    assert again.read_note() == '기존 사용자 데이터 보존'
    assert again.list_businesses()[0]['id'] == bid
    assert again.business_events(bid)[0]['action'] == 'business_added'
    assert len(again.business_types()) == 15


def test_bad_ids_and_query_limits(tmp_path):
    s = owner(tmp_path)
    for bad in (True, 0, -1, '1', 1.5):
        with pytest.raises(ValueError): s.create_business(bad, 'x', 'y')
        with pytest.raises(ValueError): s.set_business_state(bad, 'active')
        with pytest.raises(ValueError): s.business_participants(bad)
    with pytest.raises(ValueError): s.list_businesses(0)
    with pytest.raises(ValueError): s.business_events(limit=501)
    with pytest.raises(ValueError): s.add_business_type('software','중복')


def test_rejected_write_does_not_leave_partial_business_or_event(tmp_path):
    s = owner(tmp_path)
    before = len(s.business_events())
    with pytest.raises(ValueError): s.create_business(99999, 'missing type', 'goal')
    assert s.list_businesses() == []
    assert len(s.business_events()) == before
    with pytest.raises(ValueError): s.add_business_type('software', 'duplicate')
    assert len(s.business_types()) == 14
    assert len(s.business_events()) == before
