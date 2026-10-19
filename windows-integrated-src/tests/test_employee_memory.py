"""Stage47 offline employee-scoped long-term memory regression tests."""
import sqlite3
import pytest

from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def case(tmp_path):
    db=LocalStore(tmp_path/'memory.sqlite3')
    db.setup_owner('owner47','stage47-strong-password')
    a=db.add_employee_draft('memory47_a','기획 직원')
    b=db.add_employee_draft('memory47_b','개발 직원')
    return db,a,b


def test_employee_isolation_and_restart(case):
    db,a,b=case
    first=db.save_employee_memory(a,'lesson','시장 분석','고객 반응을 확인함','조사 보고서 #12',85)
    second=db.save_employee_memory(b,'fact','다른 내용','독립된 직원 지식','직원 입력',50)
    assert db.read_employee_memory(a,first)['source']=='조사 보고서 #12'
    assert [x['id'] for x in db.list_employee_memories(a)]==[first]
    assert [x['id'] for x in db.list_employee_memories(b)]==[second]
    with pytest.raises(ValueError):db.read_employee_memory(b,first)
    with pytest.raises(ValueError):db.archive_employee_memory(b,first)
    db.logout()
    restarted=LocalStore(db.path)
    with pytest.raises(AuthenticationError):restarted.list_employee_memories(a)
    restarted.login('owner47','stage47-strong-password')
    assert restarted.read_employee_memory(a,first)['content']=='고객 반응을 확인함'
    with sqlite3.connect(db.path) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()


def test_archive_immutable_not_deleted_and_search(case):
    db,a,b=case
    first=db.save_employee_memory(a,'procedure','점검 절차','재시작 전 파일 검사','내부 작업기록')
    second=db.save_employee_memory(a,'decision','자금 승인','수동 승인 요구','회의 근거',60)
    assert [m['id'] for m in db.list_employee_memories(a,query='작업기록')]==[first]
    assert len(db.list_employee_memories(a,query='%',include_archived=True))==0
    assert db.archive_employee_memory(a,first)
    assert [m['id'] for m in db.list_employee_memories(a)]==[second]
    assert db.read_employee_memory(a,first)['archived_at']
    assert [m['id'] for m in db.list_employee_memories(a,include_archived=True)]==[second,first]
    with pytest.raises(ValueError):db.archive_employee_memory(a,first)
    with sqlite3.connect(db.path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        with pytest.raises(sqlite3.IntegrityError):con.execute("UPDATE employee_long_term_memories SET content='tampered' WHERE id=?",(second,))
        with pytest.raises(sqlite3.IntegrityError):con.execute('DELETE FROM employee_long_term_memories WHERE id=?',(first,))
        with pytest.raises(sqlite3.IntegrityError):con.execute('DELETE FROM ai_employee_profiles WHERE id=?',(a,))


def test_expiry_and_inactive_employee_retains_memories(case):
    db,a,b=case
    expired=db.save_employee_memory(a,'fact','오래된 사실','유효기간 경과','외부 자료 수집',90,'2020-01-01')
    valid=db.save_employee_memory(a,'fact','장기 보존','만료 없음','사용자 확인',100)
    assert [x['id'] for x in db.list_employee_memories(a)]==[valid]
    assert {x['id'] for x in db.list_employee_memories(a,include_expired=True)}=={expired,valid}
    db.set_employee_inactive(a)
    assert db.read_employee_memory(a,expired)['content']=='유효기간 경과'
    with pytest.raises(ValueError):db.save_employee_memory(a,'fact','새 사실','본문','출처')
    db.restore_employee_draft(a)
    assert db.save_employee_memory(a,'lesson','복구','다시 작성 가능','로컬 기록')>valid


@pytest.mark.parametrize('field,value',[
    ('employee_id',0),('employee_id',True),('employee_id','1'),('employee_id',999999),
    ('kind','invalid'),('kind',None),('title',''),('title',' '),('title','x'*121),
    ('content',''),('content','x'*4001),('source',''),('source','x'*501),
    ('confidence',-1),('confidence',101),('confidence',True),('confidence',70.0),
    ('expires_on','2026-02-30'),('expires_on','2026/01/01')
])
def test_input_validation(case,field,value):
    db,a,b=case
    values=dict(employee_id=a,kind='fact',title='기억',content='본문',source='문서',confidence=70,expires_on=None)
    values[field]=value
    with pytest.raises(ValueError):db.save_employee_memory(**values)
    assert db.list_employee_memories(a)==[]


def test_read_and_list_validation_and_owner_auth(case):
    db,a,b=case
    m=db.save_employee_memory(a,'fact','사실','본문','원문')
    for bad in (0,'1',True,None):
        with pytest.raises(ValueError):db.read_employee_memory(a,bad)
        with pytest.raises(ValueError):db.archive_employee_memory(a,bad)
        with pytest.raises(ValueError):db.list_employee_memories(bad)
    for kw in ({'query':'z'*121},{'limit':0},{'limit':True},{'limit':501},{'include_expired':1},{'include_archived':1}):
        with pytest.raises(ValueError):db.list_employee_memories(a,**kw)
    db.logout()
    for action in (lambda:db.save_employee_memory(a,'fact','a','b','c'),
                   lambda:db.list_employee_memories(a),
                   lambda:db.read_employee_memory(a,m),
                   lambda:db.archive_employee_memory(a,m)):
        with pytest.raises(AuthenticationError):action()


def test_no_dependency_on_network_or_cloud(case,monkeypatch):
    import socket
    def forbidden(*args,**kwargs):raise AssertionError('outbound network forbidden')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    db,a,b=case
    mid=db.save_employee_memory(a,'lesson','오프라인','로컬에만 저장','테스트 결과')
    assert db.list_employee_memories(a)[0]['id']==mid
    assert db.archive_employee_memory(a,mid)
