"""Stage45: offline collection and non-decisional comparison of owner-entered opinions."""
import sqlite3

import pytest
from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def case(tmp_path):
    db = LocalStore(tmp_path/'stage45.sqlite3')
    db.setup_owner('stage45-owner','strong-stage45-password')
    d1=db.add_department('기획')
    d2=db.add_department('개발')
    people=[db.add_employee_draft(f'employee45_{i}',name,department_id=d1 if i==0 else d2)
            for i,name in enumerate(('Alice','Bob','Carol','Outside'))]
    mid=db.create_meeting('출시 검토','서로 다른 관점 수집')
    a1=db.add_meeting_agenda(mid,'시장 타당성')
    a2=db.add_meeting_agenda(mid,'출시 일정')
    for person in people[:3]:
        db.add_meeting_attendee(mid,person)
    return db,mid,a1,a2,people


def test_saved_opinions_organized_by_agenda_and_missing_not_counted_as_neutral(case):
    db,mid,a1,a2,people=case
    db.set_meeting_status(mid,'scheduled')
    id1=db.add_meeting_opinion(mid,a1,people[0],'찬성','조사 수치','내부 데이터','추가 조사')
    id2=db.add_meeting_opinion(mid,a1,people[1],'반대','비용 우려')
    db.add_meeting_opinion(mid,a2,people[1],'보류','출시 일정 자료 부족')
    assert id2>id1
    assert len(db.list_meeting_opinions(mid))==3
    result=db.compare_meeting_opinions(mid)
    a,b=result['agenda']
    assert a['counts']=={'찬성':1,'보류':0,'반대':1}
    assert a['has_differing_opinions'] is True
    assert a['submitted_count']==2 and a['attendee_count']==3
    assert [p['employee_id'] for p in a['missing_attendees']]==[people[2]]
    assert b['counts']=={'찬성':0,'보류':1,'반대':0}
    assert len(b['missing_attendees'])==2
    assert a['opinions'][0]['evidence']=='내부 데이터'
    assert a['opinions'][0]['alternative']=='추가 조사'
    assert '결정' in result['note']
    assert result['status']=='scheduled'


def test_draft_and_cancelled_cannot_accept_new_opinions(case):
    db,mid,a1,_,people=case
    with pytest.raises(ValueError,match='예정'):
        db.add_meeting_opinion(mid,a1,people[0],'찬성','이유')
    db.set_meeting_status(mid,'scheduled')
    db.add_meeting_opinion(mid,a1,people[0],'찬성','이유')
    db.set_meeting_status(mid,'cancelled')
    with pytest.raises(ValueError,match='예정'):
        db.add_meeting_opinion(mid,a1,people[1],'반대','이유')
    assert db.compare_meeting_opinions(mid)['status']=='cancelled'
    assert len(db.list_meeting_opinions(mid))==1


def test_duplicate_rejected_immutable(case):
    db,mid,a1,_,people=case
    db.set_meeting_status(mid,'scheduled')
    db.add_meeting_opinion(mid,a1,people[0],'찬성','근거')
    with pytest.raises(ValueError,match='이미'):
        db.add_meeting_opinion(mid,a1,people[0],'반대','바꾼 의견')
    assert db.compare_meeting_opinions(mid)['agenda'][0]['counts']['찬성']==1


def test_cross_meeting_and_non_member_rejected(case):
    db,mid,a1,_,people=case
    other=db.create_meeting('다른 회의')
    other_agenda=db.add_meeting_agenda(other,'다른 주제')
    db.set_meeting_status(mid,'scheduled')
    with pytest.raises(ValueError,match='해당 회의'):
        db.add_meeting_opinion(mid,other_agenda,people[0],'찬성','설명')
    with pytest.raises(ValueError,match='참석자'):
        db.add_meeting_opinion(mid,a1,people[3],'찬성','설명')
    assert not db.list_meeting_opinions(mid)


def test_employee_inactive_blocks_future_record_but_keeps_history(case):
    db,mid,a1,a2,people=case
    db.set_meeting_status(mid,'scheduled')
    db.add_meeting_opinion(mid,a1,people[1],'반대','비용')
    db.set_employee_inactive(people[1])
    with pytest.raises(ValueError,match='활성'):
        db.add_meeting_opinion(mid,a2,people[1],'보류','검토')
    assert len(db.list_meeting_opinions(mid))==1
    assert people[1] not in [r['employee_id'] for r in db.compare_meeting_opinions(mid)['agenda'][0]['missing_attendees']]


@pytest.mark.parametrize('bad',[0,-1,True,'1',None,1.2])
def test_invalid_ids_rejected(case,bad):
    db,mid,a1,_,people=case
    db.set_meeting_status(mid,'scheduled')
    for method in (lambda:db.add_meeting_opinion(bad,a1,people[0],'찬성','근거'),
                   lambda:db.add_meeting_opinion(mid,bad,people[0],'찬성','근거'),
                   lambda:db.add_meeting_opinion(mid,a1,bad,'찬성','근거'),
                   lambda:db.list_meeting_opinions(bad),lambda:db.compare_meeting_opinions(bad)):
        with pytest.raises(ValueError): method()


@pytest.mark.parametrize('stance',['','YES','찬성 ',None,2])
def test_unknown_stances_rejected(case,stance):
    db,mid,a1,_,people=case
    db.set_meeting_status(mid,'scheduled')
    with pytest.raises(ValueError):
        db.add_meeting_opinion(mid,a1,people[0],stance,'근거')
    assert db.list_meeting_opinions(mid)==[]


@pytest.mark.parametrize('reason',['',' ',None,'x'*2001])
def test_invalid_reason_rejected(case,reason):
    db,mid,a1,_,people=case
    db.set_meeting_status(mid,'scheduled')
    with pytest.raises(ValueError):db.add_meeting_opinion(mid,a1,people[0],'찬성',reason)
    assert db.list_meeting_opinions(mid)==[]


@pytest.mark.parametrize('kwargs',[{'evidence':'a'*501},{'alternative':'b'*1001},{'evidence':None},{'alternative':None}])
def test_optional_fields_validate_and_leave_no_partial_record(case,kwargs):
    db,mid,a1,_,people=case
    db.set_meeting_status(mid,'scheduled')
    with pytest.raises(ValueError):db.add_meeting_opinion(mid,a1,people[0],'찬성','근거',**kwargs)
    assert db.list_meeting_opinions(mid)==[]


def test_reopen_and_repeat_schema_init_keeps_previous_opinions(case):
    db,mid,a1,_,people=case
    db.set_meeting_status(mid,'scheduled')
    db.add_meeting_opinion(mid,a1,people[0],'찬성','유지할 기록')
    before=db.compare_meeting_opinions(mid)
    db.logout()
    reopened=LocalStore(db.path)
    reopened.login('stage45-owner','strong-stage45-password')
    reopened._init_schema()
    assert reopened.compare_meeting_opinions(mid)==before
    with sqlite3.connect(db.path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        assert not list(con.execute('PRAGMA foreign_key_check'))


def test_sqlite_guards_cross_meeting_write_and_immutable_rows(case):
    db,mid,a1,_,people=case
    other=db.create_meeting('다른 회의')
    other_agenda=db.add_meeting_agenda(other,'안건')
    db.set_meeting_status(mid,'scheduled')
    opinion=db.add_meeting_opinion(mid,a1,people[0],'찬성','영구 기록')
    with sqlite3.connect(db.path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        for sql,args in [
            ('UPDATE local_meeting_opinions SET stance=? WHERE id=?',('반대',opinion)),
            ('DELETE FROM local_meeting_opinions WHERE id=?',(opinion,)),
            ('''INSERT INTO local_meeting_opinions(meeting_id,agenda_id,employee_id,stance,reasoning)
                VALUES(?,?,?,?,?)''',(mid,other_agenda,people[1],'찬성','오염')),
            ('''INSERT INTO local_meeting_opinions(meeting_id,agenda_id,employee_id,stance,reasoning)
                VALUES(?,?,?,?,?)''',(mid,a1,people[3],'찬성','비참석자')),
            ('''INSERT INTO local_meeting_opinions(meeting_id,agenda_id,employee_id,stance,reasoning)
                VALUES(?,?,?,?,?)''',(mid,a1,people[0],'찬성','중복')),
        ]:
            with pytest.raises(sqlite3.IntegrityError):con.execute(sql,args)
    assert len(db.list_meeting_opinions(mid))==1


def test_authentication_enforced_on_all_entrypoints(case):
    db,mid,a1,_,people=case
    db.set_meeting_status(mid,'scheduled')
    db.logout()
    for call in (lambda:db.add_meeting_opinion(mid,a1,people[0],'찬성','근거'),
                 lambda:db.list_meeting_opinions(mid),lambda:db.compare_meeting_opinions(mid)):
        with pytest.raises(AuthenticationError):call()


def test_empty_opinion_comparison_no_false_consensus(case):
    db,mid,_,_,_=case
    db.set_meeting_status(mid,'scheduled')
    result=db.compare_meeting_opinions(mid)
    assert len(result['agenda'])==2
    assert all(a['submitted_count']==0 and not a['has_differing_opinions'] and
               len(a['missing_attendees'])==3 for a in result['agenda'])


def test_gui_methods_exist():
    from desktop.app import AIWACKWindow
    for name in ('_meeting_opinions_panel','_submit_meeting_opinion','_refresh_meeting_opinions','_select_opinion_agenda'):
        assert callable(getattr(AIWACKWindow,name))
