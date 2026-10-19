"""Stage50: evidence-based reviews and inert improvement proposals (no AI needed)."""
import sqlite3
import socket
from concurrent.futures import ThreadPoolExecutor

import pytest

from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def db(tmp_path):
    store=LocalStore(tmp_path/'company.sqlite3')
    store.setup_owner('stage50-owner','stage50-local-secure-password')
    return store


def done_task(db):
    tid=db.add_task('작업 결과물 검수','사후 평가 대상')
    db.set_task_status(tid,'in_progress')
    db.set_task_status(tid,'done')
    return tid


def review(db):
    return db.review_task_performance(done_task(db),4,'로컬 기록과 수동 검수','검수 표준을 통일해야 한다')


def test_summary_is_from_actual_tasks_not_fabricated(db):
    blank=db.task_performance_summary()
    assert blank['eligible']==0 and blank['completion_percent'] is None
    assert blank['manual_reviews']==0
    done_task(db)
    blocked=db.add_task('차단 업무')
    db.set_task_status(blocked,'blocked')
    db.add_task('미완료 업무')
    cancelled=db.add_task('취소 업무')
    db.set_task_status(cancelled,'cancelled')
    summary=db.task_performance_summary()
    assert summary['eligible']==3 and summary['completion_percent']==33.3
    assert summary['done']==1 and summary['blocked']==1 and summary['cancelled']==1


def test_review_preserves_evidence_status_and_restart(db):
    task=done_task(db)
    rid=db.review_task_performance(task,5,'단위 테스트 통과 로그','다음부터 체크리스트 사용')
    assert db.list_task_performance_reviews()[0]['task_id']==task
    assert db.list_task_performance_reviews()[0]['task_status']=='done'
    assert db.task_performance_summary()['manual_reviews']==1
    db.logout()
    restarted=LocalStore(db.path)
    with pytest.raises(AuthenticationError):restarted.list_task_performance_reviews()
    restarted.login('stage50-owner','stage50-local-secure-password')
    assert restarted.list_task_performance_reviews()[0]['evidence']=='단위 테스트 통과 로그'
    with pytest.raises(ValueError,match='이미'):restarted.review_task_performance(task,1,'근거','회고')


def test_restrict_review_to_completed_or_blocked(db):
    task=db.add_task('열린 업무')
    with pytest.raises(ValueError,match='완료 또는 차단'):db.review_task_performance(task,3,'근거','교훈')
    db.set_task_status(task,'blocked')
    assert db.review_task_performance(task,2,'차단 사유 있음','다음 단계 확인')>0
    with pytest.raises(ValueError):db.review_task_performance(999999,3,'근거','교훈')


@pytest.mark.parametrize('score',[0,6,True,3.0,'4',None,-1])
def test_reject_invalid_ratings(db,score):
    task=done_task(db)
    with pytest.raises(ValueError):db.review_task_performance(task,score,'근거','교훈')
    assert db.list_task_performance_reviews()==[]


@pytest.mark.parametrize('field,value',[
    ('evidence',''),('evidence','  '),('evidence','x'*1001),('evidence',None),
    ('lesson',''),('lesson','z'*1001),('lesson',123)
])
def test_reject_empty_or_oversized_evidence(db,field,value):
    task=done_task(db)
    args={'evidence':'근거','lesson':'교훈'}
    args[field]=value
    with pytest.raises(ValueError):db.review_task_performance(task,3,**args)
    assert db.list_task_performance_reviews()==[]


def test_proposal_review_link_and_audited_owner_decision(db):
    rid=review(db)
    pid=db.create_task_improvement(rid,'체크리스트 도입','다음 업무의 검증 항목을 수동 작성','검토 누락 감소 예상')
    assert db.task_performance_summary()['pending_proposals']==1
    assert db.list_task_improvements()[0]['state']=='proposed'
    count=len(db.list_tasks())
    assert db.decide_task_improvement(pid,'accepted','관리자가 근거 확인')
    proposal=db.list_task_improvements()[0]
    assert proposal['state']=='accepted'
    assert proposal['decision_reason']=='관리자가 근거 확인'
    assert db.task_performance_summary()['pending_proposals']==0
    assert len(db.list_tasks())==count  # Accepting a proposal does NOT create an executable task.
    with pytest.raises(ValueError,match='이미'):db.decide_task_improvement(pid,'rejected','반복')
    assert db.list_task_improvements()[0]['state']=='accepted'


def test_rejected_proposal_cannot_execute(db):
    rid=review(db)
    pid=db.create_task_improvement(rid,'중단','변경은 미실행','변경 기대')
    assert db.decide_task_improvement(pid,'rejected','검증 자료 부족')
    assert db.list_task_improvements()[0]['state']=='rejected'
    assert len(db.list_tasks())==1


@pytest.mark.parametrize('field,value',[
    ('title',''),('title','x'*161),('title',None),
    ('action',''),('action','y'*1001),('action',True),
    ('expected_result',''),('expected_result','z'*1001),('expected_result',None)
])
def test_proposal_fields_validated(db,field,value):
    rid=review(db)
    args={'title':'개선안','action':'행동','expected_result':'예상 개선'}
    args[field]=value
    with pytest.raises(ValueError):db.create_task_improvement(rid,**args)
    assert db.list_task_improvements()==[]


def test_invalid_reference_and_decision_guards(db):
    with pytest.raises(ValueError):db.create_task_improvement(999,'제목','행동','기대')
    rid=review(db)
    pid=db.create_task_improvement(rid,'제목','행동','기대')
    for decision in ('proposed','delete',None,1):
        with pytest.raises(ValueError):db.decide_task_improvement(pid,decision,'근거')
    for reason in ('','  ','x'*1001,None):
        with pytest.raises(ValueError):db.decide_task_improvement(pid,'accepted',reason)
    assert db.list_task_improvements()[0]['state']=='proposed'
    assert db.decide_task_improvement(pid,'accepted','충분한 자료')
    assert db.list_task_improvements()[0]['decision_reason']=='충분한 자료'


def test_sqlite_immutable_reviews_decisions_and_proposals(db):
    rid=review(db)
    pid=db.create_task_improvement(rid,'개선','방법','효과')
    db.decide_task_improvement(pid,'rejected','유효성 부족')
    with sqlite3.connect(db.path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        commands=[
            ('UPDATE task_performance_reviews SET rating=1 WHERE id=?',(rid,)),
            ('DELETE FROM task_performance_reviews WHERE id=?',(rid,)),
            ('UPDATE task_improvement_proposals SET title="변조" WHERE id=?',(pid,)),
            ('DELETE FROM task_improvement_proposals WHERE id=?',(pid,)),
            ('UPDATE task_improvement_decisions SET reason="변조" WHERE proposal_id=?',(pid,)),
            ('DELETE FROM task_improvement_decisions WHERE proposal_id=?',(pid,)),
        ]
        for sql,args in commands:
            with pytest.raises(sqlite3.IntegrityError): con.execute(sql,args)
        with pytest.raises(sqlite3.IntegrityError):con.execute('DELETE FROM company_tasks WHERE id=?',(db.list_task_performance_reviews()[0]['task_id'],))


def test_unauthed_and_no_network(db,monkeypatch):
    monkeypatch.setattr(socket.socket,'connect',lambda *_: (_ for _ in ()).throw(AssertionError('network forbidden')))
    rid=review(db)
    pid=db.create_task_improvement(rid,'개선','방법','기대')
    db.logout()
    operations=[lambda:db.task_performance_summary(),lambda:db.list_task_performance_reviews(),
        lambda:db.review_task_performance(1,3,'근거','교훈'),
        lambda:db.create_task_improvement(rid,'제목','행동','기대'),
        lambda:db.list_task_improvements(),lambda:db.decide_task_improvement(pid,'accepted','사유')]
    for operation in operations:
        with pytest.raises(AuthenticationError):operation()


def test_atomic_concurrent_duplicate_review_and_proposal_decision(db):
    task=done_task(db)
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures=[executor.submit(db.review_task_performance,task,3,'검증','회고') for _ in range(3)]
        results=[]
        for f in futures:
            try:results.append(f.result())
            except ValueError:pass
    assert len(results)==1
    pid=db.create_task_improvement(results[0],'개선','방식','효과')
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures=[executor.submit(db.decide_task_improvement,pid,'accepted','승인') for _ in range(2)]
        outcomes=[]
        for f in futures:
            try:outcomes.append(f.result())
            except ValueError:pass
    assert outcomes==[True]
    with sqlite3.connect(db.path) as con:
        assert con.execute('SELECT COUNT(*) FROM task_improvement_decisions WHERE proposal_id=?',(pid,)).fetchone()[0]==1


def test_limits_and_schema_initialization_idempotent(db):
    review(db)
    for lim in (0,-1,501,True,'10'):
        with pytest.raises(ValueError):db.list_task_performance_reviews(lim)
        with pytest.raises(ValueError):db.list_task_improvements(lim)
    LocalStore(db.path)
    assert len(db.list_task_performance_reviews())==1
