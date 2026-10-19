"""Stage42: owner-only, persisted department conversations and isolation."""
import sqlite3
import pytest

from desktop.storage import AuthenticationError, LocalStore


@pytest.fixture
def store(tmp_path):
    db = LocalStore(tmp_path / 'department_chat.sqlite3')
    db.setup_owner('stage42_owner', 'secure-stage42-password')
    return db


def members(db):
    first = db.add_department('연구개발부')
    second = db.add_department('품질관리부')
    alice = db.add_employee_draft('chat42_alice', 'Alice', department_id=first)
    bob = db.add_employee_draft('chat42_bob', 'Bob', department_id=first)
    carol = db.add_employee_draft('chat42_carol', 'Carol', department_id=second)
    return first, second, alice, bob, carol


def test_scoped_conversation_and_reopen(store):
    a, b, alice, bob, carol = members(store)
    first = store.send_department_message(a, alice, '  일정 확인  ')
    second = store.send_department_message(a, bob, '확인 완료')
    third = store.send_department_message(b, carol, '별도 부서 검토')
    room_a = store.list_department_messages(a)
    assert [m['id'] for m in room_a] == [first, second]
    assert [m['body'] for m in room_a] == ['일정 확인', '확인 완료']
    assert room_a[0]['sender_name'] == 'Alice'
    assert [m['id'] for m in store.list_department_messages(b)] == [third]
    assert [m['id'] for m in store.list_department_messages(a, limit=1)] == [second]
    store.logout()
    with pytest.raises(AuthenticationError):
        store.list_department_messages(a)
    reloaded = LocalStore(store.path)
    reloaded.login('stage42_owner', 'secure-stage42-password')
    assert [m['id'] for m in reloaded.list_department_messages(a)] == [first, second]
    reloaded._init_schema()  # idempotent migration; old messages remain
    assert len(reloaded.list_department_messages(a)) == 2
    with sqlite3.connect(store.path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        assert not con.execute('PRAGMA foreign_key_check').fetchall()


def test_membership_and_inactivation(store):
    a, b, alice, bob, carol = members(store)
    store.send_department_message(a, alice, '기존 기록')
    with pytest.raises(ValueError):
        store.send_department_message(a, carol, '다른 부서 직원')
    store.set_employee_inactive(bob)
    with pytest.raises(ValueError):
        store.send_department_message(a, bob, '비활성 직원')
    store.update_employee_record(alice, 'Alice', department_id=b)
    with pytest.raises(ValueError):
        store.send_department_message(a, alice, '이전 부서')
    assert len(store.list_department_messages(a)) == 1  # immutable history
    store.send_department_message(b, alice, '이동 후 기록')
    assert len(store.list_department_messages(b)) == 1
    with pytest.raises(ValueError):
        store.delete_department(a)  # durable message protects history


@pytest.mark.parametrize('invalid', [0, -1, True, '1', None, 2.5])
def test_invalid_ids_rejected(store, invalid):
    a, _, alice, _, _ = members(store)
    with pytest.raises(ValueError):
        store.send_department_message(invalid, alice, 'hello')
    with pytest.raises(ValueError):
        store.send_department_message(a, invalid, 'hello')
    with pytest.raises(ValueError):
        store.list_department_messages(invalid)


@pytest.mark.parametrize('body', ['', ' ', None, 'X'*4001])
def test_body_validation_and_atomicity(store, body):
    a, _, alice, _, _ = members(store)
    with pytest.raises(ValueError):
        store.send_department_message(a, alice, body)
    assert store.list_department_messages(a) == []


def test_unknown_department_and_employee(store):
    a, _, alice, _, _ = members(store)
    for department, employee in ((999, alice), (a, 999)):
        with pytest.raises(ValueError):
            store.send_department_message(department, employee, 'hello')
    with pytest.raises(ValueError):
        store.list_department_messages(999)
    for bad in (0, 501, True, '200'):
        with pytest.raises(ValueError):
            store.list_department_messages(a, limit=bad)


def test_owner_permission_and_sql_trigger(store):
    a, b, alice, _, carol = members(store)
    with sqlite3.connect(store.path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('INSERT INTO department_chat_messages(department_id,sender_id,body) VALUES (?,?,?)', (a, carol, 'forged'))
    mid = store.send_department_message(a, alice, '원본')
    with sqlite3.connect(store.path) as con:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('UPDATE department_chat_messages SET body=? WHERE id=?', ('altered', mid))
    store.logout()
    with pytest.raises(AuthenticationError):
        store.send_department_message(a, alice, 'forbidden')
    with pytest.raises(AuthenticationError):
        store.list_department_messages(b)


def test_existing_direct_messages_and_company_data_preserved(store):
    a, _, alice, bob, _ = members(store)
    private_id = store.send_direct_message(alice, bob, '기존 제목', '기존 본문')
    store.save_note('보존할 메모')
    store.send_department_message(a, alice, '별도 부서 대화')
    assert store.list_direct_messages()[0]['id'] == private_id
    assert store.read_note() == '보존할 메모'


def test_queue_and_messaging_gui_methods_remain_bound():
    # Regression: inherited Stage41 archive put methods under module run(),
    # breaking the authenticated desktop immediately after login.
    from desktop.app import AIWACKWindow
    for method in ('_task_queue_panel', 'refresh_task_queue', '_direct_messages_panel',
                   '_department_chat_panel', '_send_department_chat', '_refresh_department_chat'):
        assert callable(getattr(AIWACKWindow, method))
