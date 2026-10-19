"""Stage44: offline agenda and attendance constraints, auth, and persistence."""
import sqlite3
import pytest
from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def store(tmp_path):
    store = LocalStore(tmp_path/'meetings.sqlite3')
    store.setup_owner('owner44','strong-stage44-password')
    return store


def employees(db):
    dep1 = db.add_department('전략기획')
    dep2 = db.add_department('개발')
    return (db.add_employee_draft('meeting_alice','Alice',department_id=dep1),
            db.add_employee_draft('meeting_bob','Bob',department_id=dep2),
            db.add_employee_draft('meeting_carol','Carol',department_id=dep2))


def test_agenda_and_participants_persist_across_reopen(store):
    alice,bob,_ = employees(store)
    mid = store.create_meeting('상품 기획 검토', '출시 일정 검토')
    store.add_meeting_agenda(mid,'시장 검증')
    store.add_meeting_agenda(mid,'일정 비교')
    store.add_meeting_attendee(mid,alice)
    store.add_meeting_attendee(mid,bob)
    store.set_meeting_status(mid,'scheduled')
    view = store.read_meeting(mid)
    assert view['status']=='scheduled'
    assert [a['topic'] for a in view['agenda']]==['시장 검증','일정 비교']
    assert {p['display_name'] for p in view['attendees']}=={'Alice','Bob'}
    assert store.list_meetings()[0]['attendee_count']==2
    store.logout()
    reload = LocalStore(store.path)
    reload.login('owner44','strong-stage44-password')
    assert reload.read_meeting(mid)==view
    reload._init_schema()
    assert len(reload.read_meeting(mid)['agenda'])==2
    with sqlite3.connect(store.path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        assert not con.execute('PRAGMA foreign_key_check').fetchall()


def test_meeting_requires_two_active_staff_and_an_agenda(store):
    alice,bob,_ = employees(store)
    mid=store.create_meeting('검토')
    with pytest.raises(ValueError,match='안건'):
        store.set_meeting_status(mid,'scheduled')
    store.add_meeting_agenda(mid,'진행 상황')
    store.add_meeting_attendee(mid,alice)
    with pytest.raises(ValueError,match='참석자'):
        store.set_meeting_status(mid,'scheduled')
    store.add_meeting_attendee(mid,bob)
    store.set_employee_inactive(bob)
    with pytest.raises(ValueError,match='활성'):
        store.set_meeting_status(mid,'scheduled')
    assert store.read_meeting(mid)['status']=='draft'
    store.remove_meeting_attendee(mid,bob)
    assert len(store.read_meeting(mid)['attendees'])==1


def test_ready_meeting_freezes_roster_and_agenda_and_cancelled_is_terminal(store):
    alice,bob,carol=employees(store)
    mid=store.create_meeting('고정')
    store.add_meeting_agenda(mid,'검토')
    store.add_meeting_attendee(mid,alice)
    store.add_meeting_attendee(mid,bob)
    store.set_meeting_status(mid,'scheduled')
    for action in (lambda:store.add_meeting_agenda(mid,'추가'),
                   lambda:store.add_meeting_attendee(mid,carol),
                   lambda:store.remove_meeting_attendee(mid,alice)):
        with pytest.raises(ValueError): action()
    store.set_meeting_status(mid,'cancelled')
    with pytest.raises(ValueError): store.set_meeting_status(mid,'scheduled')
    with pytest.raises(ValueError): store.add_meeting_agenda(mid,'변경')
    assert store.read_meeting(mid)['status']=='cancelled'


@pytest.mark.parametrize('bad',[0,-1,True,'1',None,1.2])
def test_invalid_meeting_and_employee_ids(store,bad):
    mid=store.create_meeting('검증')
    with pytest.raises(ValueError): store.read_meeting(bad)
    with pytest.raises(ValueError): store.add_meeting_agenda(bad,'topic')
    with pytest.raises(ValueError): store.add_meeting_attendee(mid,bad)


@pytest.mark.parametrize('title',['',' ',None,'X'*121])
def test_invalid_title_rejected(store,title):
    with pytest.raises(ValueError): store.create_meeting(title)
    assert store.list_meetings()==[]


def test_validation_no_partial_writes_and_limits(store):
    alice,bob,_=employees(store)
    mid=store.create_meeting('안건')
    for invalid in ('', '  ', 'X'*501, None):
        with pytest.raises(ValueError): store.add_meeting_agenda(mid,invalid)
    for index in range(20):
        store.add_meeting_agenda(mid,f'안건 {index+1}')
    with pytest.raises(ValueError): store.add_meeting_agenda(mid,'초과')
    assert len(store.read_meeting(mid)['agenda'])==20
    store.add_meeting_attendee(mid,alice)
    with pytest.raises(ValueError,match='이미'):
        store.add_meeting_attendee(mid,alice)
    with pytest.raises(ValueError): store.add_meeting_attendee(mid,99999)
    with pytest.raises(ValueError): store.remove_meeting_attendee(mid,bob)
    assert len(store.read_meeting(mid)['attendees'])==1


def test_database_guards_direct_sql_mutation(store):
    alice,bob,carol=employees(store)
    mid=store.create_meeting('SQL 보호')
    agenda_id=store.add_meeting_agenda(mid,'일정')
    store.add_meeting_attendee(mid,alice)
    store.add_meeting_attendee(mid,bob)
    with sqlite3.connect(store.path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('UPDATE local_meeting_agenda SET topic=? WHERE id=?',('위조',agenda_id))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('UPDATE local_meeting_attendees SET employee_id=? WHERE meeting_id=? AND employee_id=?',
                        (carol,mid,alice))
        # A single person never qualifies for scheduled state.
        con.execute('DELETE FROM local_meeting_attendees WHERE meeting_id=? AND employee_id=?',(mid,bob))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("UPDATE local_ai_meetings SET status='scheduled' WHERE id=?",(mid,))
    store.add_meeting_attendee(mid,bob)
    store.set_meeting_status(mid,'scheduled')
    with sqlite3.connect(store.path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('DELETE FROM local_meeting_attendees WHERE meeting_id=? AND employee_id=?',(mid,alice))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('DELETE FROM local_meeting_agenda WHERE id=?',(agenda_id,))
    assert len(store.read_meeting(mid)['attendees'])==2


def test_owner_login_required_for_all_meeting_functions(store):
    alice,_,_=employees(store)
    mid=store.create_meeting('권한')
    store.logout()
    calls=(lambda:store.create_meeting('금지'),lambda:store.list_meetings(),
           lambda:store.read_meeting(mid),lambda:store.add_meeting_agenda(mid,'금지'),
           lambda:store.add_meeting_attendee(mid,alice),
           lambda:store.remove_meeting_attendee(mid,alice),
           lambda:store.set_meeting_status(mid,'cancelled'))
    for callback in calls:
        with pytest.raises(AuthenticationError): callback()


def test_gui_methods_available():
    from desktop.app import AIWACKWindow
    for method in ('_meetings_panel','_create_meeting','_add_meeting_attendee',
                   '_remove_meeting_attendee','_schedule_meeting','_cancel_meeting',
                   '_add_meeting_agenda','_refresh_meetings','_refresh_meeting_detail'):
        assert callable(getattr(AIWACKWindow,method))
