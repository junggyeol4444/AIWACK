"""Stage43 project-specific collaboration: storage isolation, access, and recovery."""
import sqlite3
import pytest

from desktop.storage import AuthenticationError, LocalStore


@pytest.fixture
def store(tmp_path):
    instance = LocalStore(tmp_path / 'project.sqlite3')
    instance.setup_owner('owner43', 'stage43-strong-password')
    return instance


def people(store):
    a = store.add_department('운영팀')
    b = store.add_department('연구팀')
    alice = store.add_employee_draft('alice43', 'Alice', department_id=a)
    bob = store.add_employee_draft('bob43', 'Bob', department_id=b)
    carol = store.add_employee_draft('carol43', 'Carol', department_id=b)
    return alice, bob, carol


def test_multiple_projects_and_independent_participants(store):
    alice, bob, carol = people(store)
    first = store.create_project_room('상품 제작', '첫째 업무')
    second = store.create_project_room('서비스 연구')
    store.add_project_participant(first, alice)
    store.add_project_participant(first, bob)
    store.add_project_participant(second, bob)
    store.add_project_participant(second, carol)
    m1 = store.send_project_message(first, alice, '기획 초안')
    m2 = store.send_project_message(first, bob, '검토하겠습니다')
    m3 = store.send_project_message(second, bob, '다른 프로젝트')
    assert [m['id'] for m in store.list_project_messages(first)] == [m1, m2]
    assert [m['id'] for m in store.list_project_messages(second)] == [m3]
    assert store.list_project_messages(first, limit=1)[0]['id'] == m2
    assert store.list_project_messages(first)[0]['sender_name'] == 'Alice'
    assert [r['participant_count'] for r in store.list_project_rooms()] == [2, 2]
    assert len(store.list_project_participants(second)) == 2
    with pytest.raises(ValueError):
        store.send_project_message(second, alice, '참여하지 않음')


def test_participant_removal_keeps_history_but_restricts_new_messages(store):
    alice, bob, _ = people(store)
    room = store.create_project_room('기록 보존')
    store.add_project_participant(room, alice)
    original = store.send_project_message(room, alice, '이전 기록')
    store.remove_project_participant(room, alice)
    with pytest.raises(ValueError):
        store.send_project_message(room, alice, '탈퇴 후 위조')
    assert store.list_project_messages(room)[0]['id'] == original
    assert store.list_project_participants(room) == []
    store.add_project_participant(room, alice)
    assert store.send_project_message(room, alice, '복귀 후 기록') > original
    store.set_employee_inactive(alice)
    with pytest.raises(ValueError):
        store.send_project_message(room, alice, '비활성 직원')
    with pytest.raises(ValueError):
        store.add_project_participant(room, alice)
    assert len(store.list_project_messages(room)) == 2


def test_project_cross_department_cooperation_and_transfer(store):
    alice, bob, _ = people(store)
    room = store.create_project_room('공동 개발')
    store.add_project_participant(room, alice)
    store.add_project_participant(room, bob)
    store.update_employee_record(alice, 'Alice 이동', department_id=None)
    assert store.send_project_message(room, alice, '부서 이동 후에도 참여') > 0
    assert len(store.list_project_messages(room)) == 1


def test_schema_migration_idempotent_and_reopen(store):
    alice, _, _ = people(store)
    room = store.create_project_room('영구 저장')
    store.add_project_participant(room, alice)
    ident = store.send_project_message(room, alice, '저장된 메시지')
    store.save_note('원본 메모')
    store._init_schema()
    store.logout()
    with pytest.raises(AuthenticationError):
        store.list_project_rooms()
    with pytest.raises(AuthenticationError):
        store.send_project_message(room, alice, '금지')
    reopened = LocalStore(store.path)
    reopened.login('owner43', 'stage43-strong-password')
    assert reopened.list_project_messages(room)[0]['id'] == ident
    assert reopened.list_project_participants(room)[0]['employee_id'] == alice
    assert reopened.read_note() == '원본 메모'
    with sqlite3.connect(store.path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        assert con.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('invalid',[0, -1, True, '1', None, 1.3])
def test_invalid_project_and_sender_ids(store,invalid):
    alice, _, _ = people(store)
    room = store.create_project_room('ID 유효성')
    for action in (lambda: store.add_project_participant(invalid, alice),
                   lambda: store.remove_project_participant(invalid, alice),
                   lambda: store.list_project_participants(invalid),
                   lambda: store.list_project_messages(invalid),
                   lambda: store.send_project_message(invalid, alice, '본문'),
                   lambda: store.add_project_participant(room, invalid)):
        with pytest.raises(ValueError):
            action()
    with pytest.raises(ValueError):
        store.list_project_messages(99999)


@pytest.mark.parametrize('bad', ['', ' ', None, 'X'*4001])
def test_invalid_message_and_project_names(store,bad):
    alice, _, _ = people(store)
    room = store.create_project_room('제목')
    store.add_project_participant(room, alice)
    with pytest.raises(ValueError):
        store.send_project_message(room, alice, bad)
    with pytest.raises(ValueError):
        store.create_project_room(bad)
    assert store.list_project_messages(room) == []


def test_duplicate_participants_and_atomic_rejection(store):
    alice, _, _ = people(store)
    room = store.create_project_room('중복 제한')
    store.add_project_participant(room, alice)
    with pytest.raises(ValueError):
        store.add_project_participant(room, alice)
    with pytest.raises(ValueError):
        store.remove_project_participant(room, 99999)
    assert len(store.list_project_participants(room)) == 1
    assert store.list_project_messages(room) == []


def test_sqlite_guards_against_member_spoofing_and_message_rewrite(store):
    alice, bob, _ = people(store)
    room = store.create_project_room('DB 보호')
    store.add_project_participant(room, alice)
    ident = store.send_project_message(room, alice, '원래 내용')
    with sqlite3.connect(store.path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('UPDATE local_project_participants SET employee_id=? WHERE project_id=? AND employee_id=?',
                        (bob,room,alice))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('INSERT INTO local_project_messages(project_id,sender_id,body) VALUES(?,?,?)', (room,bob,'위조'))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('UPDATE local_project_messages SET body=? WHERE id=?', ('변경',ident))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('DELETE FROM local_project_messages WHERE id=?', (ident,))
    assert store.list_project_messages(room)[0]['body'] == '원래 내용'


def test_query_bounds_and_permissions(store):
    alice, _, _ = people(store)
    room = store.create_project_room('권한')
    store.add_project_participant(room, alice)
    for bad in (0, 501, True, '10', -3):
        with pytest.raises(ValueError):
            store.list_project_messages(room, limit=bad)
    store.logout()
    for action in (lambda: store.create_project_room('unauth'),
                   lambda: store.list_project_rooms(),
                   lambda: store.add_project_participant(room,alice),
                   lambda: store.remove_project_participant(room,alice),
                   lambda: store.list_project_participants(room),
                   lambda: store.list_project_messages(room)):
        with pytest.raises(AuthenticationError):
            action()


def test_gui_methods_bound():
    from desktop.app import AIWACKWindow
    for name in ('_project_chat_panel','_create_project_chat_room','_add_project_chat_participant',
                 '_remove_project_chat_participant','_send_project_chat','_refresh_project_chat',
                 '_refresh_project_chat_rooms'):
        assert callable(getattr(AIWACKWindow,name))
