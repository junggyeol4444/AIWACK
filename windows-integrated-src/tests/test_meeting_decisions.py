"""Stage46 decision and follow-up integration, durable data, guards and authorization."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def case(tmp_path):
    db=LocalStore(tmp_path/'meeting_decisions.sqlite3')
    db.setup_owner('owner-stage46','correct-stage46-password')
    dep=db.add_department('전략')
    staff=[db.add_employee_draft(f'staff46_{i}',name,department_id=dep)
           for i,name in enumerate(['기획 담당','개발 담당','검수 담당','외부 직원'])]
    meeting=db.create_meeting('제품 출시 심사','의견을 수집해 소유자가 결정')
    agenda1=db.add_meeting_agenda(meeting,'출시 여부')
    agenda2=db.add_meeting_agenda(meeting,'다음 일정')
    for person in staff[:3]:db.add_meeting_attendee(meeting,person)
    db.set_meeting_status(meeting,'scheduled')
    return db,meeting,agenda1,agenda2,staff


def record(db,m,a,staff):
    db.add_meeting_opinion(m,a,staff[0],'찬성','일정 확보')
    db.add_meeting_opinion(m,a,staff[1],'반대','품질 우려')


def test_owner_decision_records_dissent_and_missing_without_auto_vote(case):
    db,m,a,_,staff=case
    record(db,m,a,staff)
    dec=db.decide_meeting_agenda(m,a,'approved','의견 차이를 검토한 후 시험 출시하기로 결정',True)
    data=db.list_meeting_decisions(m)[0]
    assert data['id']==dec and data['outcome']=='approved'
    assert data['opinions_count']==2 and data['missing_count']==1
    assert data['rationale'].startswith('의견 차이') and data['task_id'] is None
    assert db.list_tasks()==[]
    assert db.read_meeting(m)['status']=='scheduled'


def test_decision_and_followup_linked_atomically_with_assignee_and_history(case):
    db,m,a,_,staff=case
    record(db,m,a,staff)
    dec=db.decide_meeting_agenda(m,a,'approved','허용된 내부 검토만 진행',True)
    task=db.create_meeting_followup(dec,staff[0],'출시 점검표 작성','로컬 파일 점검')
    data=db.read_task(task)
    assert data['status']=='todo' and data['title']=='출시 점검표 작성'
    assert db.read_task_routing(task)['employee_id']==staff[0]
    assert db.list_task_status_events(task)[0]['new_status']=='todo'
    assert db.list_task_assignment_events(task)[0]['employee_id']==staff[0]
    decisions=db.list_meeting_decisions(m)
    assert decisions[0]['task_id']==task and decisions[0]['assignee_id']==staff[0]
    with pytest.raises(ValueError,match='이미'):db.create_meeting_followup(dec,staff[1],'반복')
    assert len(db.list_tasks())==1
    with pytest.raises(sqlite3.IntegrityError):db.delete_task(task)


@pytest.mark.parametrize('outcome',['deferred','rejected'])
def test_only_approved_has_followup(case,outcome):
    db,m,a,_,staff=case
    record(db,m,a,staff)
    dec=db.decide_meeting_agenda(m,a,outcome,'의견 고려 후 연기 또는 반려',True)
    with pytest.raises(ValueError,match='채택'):db.create_meeting_followup(dec,staff[0],'후속 업무')
    assert not db.list_tasks()


def test_no_votes_no_decision_and_unauthorized_not_silent(case):
    db,m,a,_,staff=case
    with pytest.raises(ValueError,match='의견'):db.decide_meeting_agenda(m,a,'approved','검토',True)
    db.add_meeting_opinion(m,a,staff[0],'찬성','이유')
    with pytest.raises(ValueError,match='확인'):db.decide_meeting_agenda(m,a,'approved','검토',False)
    assert not db.list_meeting_decisions(m)


@pytest.mark.parametrize('outcome',['',None,'찬성','APPROVED','approved ','cancelled',0])
def test_invalid_outcome(case,outcome):
    db,m,a,_,staff=case
    db.add_meeting_opinion(m,a,staff[0],'찬성','이유')
    with pytest.raises(ValueError):db.decide_meeting_agenda(m,a,outcome,'근거',True)
    assert not db.list_meeting_decisions(m)


@pytest.mark.parametrize('reason',['',None,' ','x'*2001])
def test_invalid_rationale(case,reason):
    db,m,a,_,staff=case
    db.add_meeting_opinion(m,a,staff[0],'찬성','이유')
    with pytest.raises(ValueError):db.decide_meeting_agenda(m,a,'approved',reason,True)


def test_wrong_agenda_and_wrong_meeting_cancelled(case):
    db,m,a,_,staff=case
    db.add_meeting_opinion(m,a,staff[0],'찬성','이유')
    m2=db.create_meeting('다른 회의')
    a2=db.add_meeting_agenda(m2,'무관')
    with pytest.raises(ValueError,match='해당 회의'):db.decide_meeting_agenda(m,a2,'approved','근거',True)
    db.set_meeting_status(m,'cancelled')
    with pytest.raises(ValueError,match='예정'):db.decide_meeting_agenda(m,a,'approved','근거',True)
    assert not db.list_meeting_decisions(m)


def test_cancel_after_decision_prevents_followup(case):
    db,m,a,_,staff=case
    db.add_meeting_opinion(m,a,staff[0],'찬성','이유')
    dec=db.decide_meeting_agenda(m,a,'approved','결정',True)
    db.set_meeting_status(m,'cancelled')
    with pytest.raises(ValueError,match='취소'):db.create_meeting_followup(dec,staff[0],'업무')
    assert db.list_meeting_decisions(m)[0]['id']==dec
    assert not db.list_tasks()


def test_non_attendee_and_inactive_assignee_rejected_atomically(case):
    db,m,a,_,staff=case
    db.add_meeting_opinion(m,a,staff[0],'찬성','이유')
    dec=db.decide_meeting_agenda(m,a,'approved','결정',True)
    with pytest.raises(ValueError,match='참석자'):db.create_meeting_followup(dec,staff[3],'잘못된 업무')
    db.set_employee_inactive(staff[1])
    with pytest.raises(ValueError,match='참석자'):db.create_meeting_followup(dec,staff[1],'비활성 업무')
    assert not db.list_tasks()
    assert db.list_meeting_decisions(m)[0]['task_id'] is None


@pytest.mark.parametrize('bad',[None,0,-1,True,'1',1.5])
def test_invalid_ids_and_authenticated_entries(case,bad):
    db,m,a,_,staff=case
    db.add_meeting_opinion(m,a,staff[0],'찬성','이유')
    for call in (lambda:db.decide_meeting_agenda(bad,a,'approved','근거',True),
                 lambda:db.decide_meeting_agenda(m,bad,'approved','근거',True),
                 lambda:db.create_meeting_followup(bad,staff[0],'업무'),
                 lambda:db.list_meeting_decisions(bad)):
        with pytest.raises(ValueError):call()


def test_invalid_followup_title_rolls_back_and_can_retry(case):
    db,m,a,_,staff=case
    db.add_meeting_opinion(m,a,staff[0],'찬성','이유')
    dec=db.decide_meeting_agenda(m,a,'approved','검토 완료',True)
    for title in ('','x'*121,None):
        with pytest.raises(ValueError):db.create_meeting_followup(dec,staff[0],title)
    assert db.list_tasks()==[]
    assert db.create_meeting_followup(dec,staff[0],'유효 업무')>0


def test_duplicate_decision_prevented_and_immutable_sqlite_guards(case):
    db,m,a,_,staff=case
    record(db,m,a,staff)
    dec=db.decide_meeting_agenda(m,a,'deferred','결정 기록',True)
    with pytest.raises(ValueError,match='이미'):db.decide_meeting_agenda(m,a,'approved','다른 결정',True)
    with sqlite3.connect(db.path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        for sql,args in [
            ('UPDATE local_meeting_decisions SET outcome=? WHERE id=?',('approved',dec)),
            ('DELETE FROM local_meeting_decisions WHERE id=?',(dec,)),
            ('''INSERT INTO local_meeting_decisions(meeting_id,agenda_id,outcome,rationale,opinions_count,missing_count,dissent_acknowledged)
              VALUES(?,?,?,?,?,?,?)''',(m,a,'approved','가짜',2,0,1))]:
            with pytest.raises(sqlite3.IntegrityError):con.execute(sql,args)
    assert len(db.list_meeting_decisions(m))==1


def test_duplicate_followup_is_race_safe(case):
    db,m,a,_,staff=case
    db.add_meeting_opinion(m,a,staff[0],'찬성','이유')
    dec=db.decide_meeting_agenda(m,a,'approved','결정',True)
    def attempt(i):
        try:return db.create_meeting_followup(dec,staff[0],f'후속 업무 {i}')
        except ValueError:return None
    with ThreadPoolExecutor(max_workers=3) as pool:
        result=list(pool.map(attempt,range(3)))
    assert sum(x is not None for x in result)==1
    assert len(db.list_tasks())==1


def test_sqlite_followup_link_and_relogin_persistence(case):
    db,m,a,_,staff=case
    db.add_meeting_opinion(m,a,staff[0],'찬성','이유')
    dec=db.decide_meeting_agenda(m,a,'approved','결정',True)
    tid=db.create_meeting_followup(dec,staff[0],'검증 완료')
    with sqlite3.connect(db.path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        for sql,args in [
            ('DELETE FROM local_meeting_followups WHERE decision_id=?',(dec,)),
            ('UPDATE local_meeting_followups SET assignee_id=? WHERE decision_id=?',(staff[1],dec))]:
            with pytest.raises(sqlite3.IntegrityError):con.execute(sql,args)
        assert not list(con.execute('PRAGMA foreign_key_check'))
    db.logout()
    restarted=LocalStore(db.path)
    restarted.login('owner-stage46','correct-stage46-password')
    restarted._init_schema()
    assert restarted.list_meeting_decisions(m)[0]['task_id']==tid
    assert restarted.read_task_routing(tid)['employee_id']==staff[0]
    restarted.logout()
    for call in (lambda:restarted.list_meeting_decisions(m),
                 lambda:restarted.decide_meeting_agenda(m,a,'approved','근거',True),
                 lambda:restarted.create_meeting_followup(dec,staff[0],'업무')):
        with pytest.raises(AuthenticationError):call()


def test_guards_prevent_unauthorized_direct_link_and_no_task_created(case):
    db,m,a,_,staff=case
    db.add_meeting_opinion(m,a,staff[0],'찬성','이유')
    dec=db.decide_meeting_agenda(m,a,'approved','결정',True)
    task=db.add_task('할 일')  # Unassigned: cannot forge a meeting follow-up link
    with sqlite3.connect(db.path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('INSERT INTO local_meeting_followups(decision_id,task_id,assignee_id) VALUES(?,?,?)',
                        (dec,task,staff[0]))


def test_gui_actions_declared():
    from desktop.app import AIWACKWindow
    for name in ('_meeting_decisions_panel','_save_meeting_decision','_refresh_meeting_decisions',
                 '_select_meeting_decision','_create_meeting_followup'):
        assert callable(getattr(AIWACKWindow,name))


def test_opinions_are_frozen_after_decision(case):
    db,m,a,_,staff=case
    db.add_meeting_opinion(m,a,staff[0],'찬성','근거')
    db.decide_meeting_agenda(m,a,'deferred','추가 논의는 새 안건에서 진행',True)
    with pytest.raises(sqlite3.IntegrityError,match='decided agenda'):
        db.add_meeting_opinion(m,a,staff[1],'반대','늦은 의견')
    assert len(db.list_meeting_opinions(m))==1
