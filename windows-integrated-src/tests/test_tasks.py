"""Stage23 owner-only work tracking: no autonomous execution or network."""
import sqlite3

import pytest

from desktop.storage import LocalStore, AuthenticationError

USER, PASSWORD = "stage23_owner", "password-that-is-long-2026"


def ready(tmp_path):
    db = LocalStore(tmp_path / "app.sqlite3")
    db.setup_owner(USER, PASSWORD)
    goal = db.add_goal("배송 준비")
    plan = db.add_work_plan(goal, "실행 계획", "", ["문서 준비", "검토"])
    return db, goal, plan


def test_created_task_and_history_and_reopen(tmp_path):
    db, goal, plan = ready(tmp_path)
    task_id = db.add_task("기술 문서", "첫 초안", plan)
    assert task_id > 0
    assert db.read_task(task_id)["status"] == "todo"
    assert db.read_task(task_id)["plan_id"] == plan
    assert db.list_tasks(plan)[0]["plan_title"] == "실행 계획"
    assert db.list_task_status_events(task_id)[0]["old_status"] is None
    assert db.list_task_status_events(task_id)[0]["new_status"] == "todo"
    db.logout()
    reopened = LocalStore(db.path)
    with pytest.raises(AuthenticationError):
        reopened.list_tasks()
    reopened.login(USER,PASSWORD)
    assert reopened.read_task(task_id)["title"] == "기술 문서"
    assert len(reopened.list_task_status_events(task_id)) == 1


def test_unlinked_task_and_relink(tmp_path):
    db, _, plan = ready(tmp_path)
    task = db.add_task("독립 업무")
    assert db.read_task(task)["plan_id"] is None
    db.update_task(task,"연결된 업무","새 설명",plan)
    assert db.read_task(task)["plan_id"] == plan
    assert db.read_task(task)["description"] == "새 설명"
    db.update_task(task,"독립 업무","",None)
    assert db.list_tasks(plan) == []
    assert db.read_task(task)["plan_id"] is None


def test_status_history_and_completed_at(tmp_path):
    db, _, _ = ready(tmp_path)
    task = db.add_task("업무")
    for state in ("in_progress", "blocked", "in_progress", "done"):
        db.set_task_status(task,state)
    assert db.read_task(task)["status"] == "done"
    assert db.read_task(task)["completed_at"]
    assert [(x["old_status"],x["new_status"]) for x in db.list_task_status_events(task)] == [
        (None,"todo"),("todo","in_progress"),("in_progress","blocked"),
        ("blocked","in_progress"),("in_progress","done")]
    db.set_task_status(task,"todo")
    assert db.read_task(task)["completed_at"] is None
    db.update_task(task,"재개 업무")
    assert db.read_task(task)["title"] == "재개 업무"


def test_invalid_transitions_do_not_create_events(tmp_path):
    db,_,_ = ready(tmp_path)
    task = db.add_task("처음")
    for state in ("done","todo","running","",None,1):
        with pytest.raises(ValueError):
            db.set_task_status(task,state)
    assert db.read_task(task)["status"] == "todo"
    assert len(db.list_task_status_events(task)) == 1
    db.set_task_status(task,"cancelled")
    with pytest.raises(ValueError):
        db.set_task_status(task,"done")
    with pytest.raises(ValueError):
        db.update_task(task,"수정 금지")
    db.set_task_status(task,"todo")
    assert db.read_task(task)["status"] == "todo"


@pytest.mark.parametrize("title,description,plan", [
    ("", "", None), ("  ","",None),("a"*121,"",None),
    ("정상","a"*1001,None),("정상","",True),("정상","",0),
    ("정상","",-5),("정상","","3"),("정상","",999999),
])
def test_invalid_creation_no_side_effect(tmp_path,title,description,plan):
    db,_,_=ready(tmp_path)
    with pytest.raises(ValueError):
        db.add_task(title,description,plan)
    assert db.list_tasks() == []


def test_failed_edit_preserves_original(tmp_path):
    db,_,plan=ready(tmp_path)
    task=db.add_task("원본","계획",plan)
    for call in (lambda:db.update_task(task,"수정","",345667),
                 lambda:db.update_task(task,"","",None),
                 lambda:db.update_task(task,"수정","z"*1001,None)):
        with pytest.raises(ValueError):
            call()
    assert db.read_task(task)["title"]=="원본"
    assert db.read_task(task)["plan_id"]==plan
    assert len(db.list_task_status_events(task))==1


def test_existing_plan_restrict_until_task_unlinked(tmp_path):
    db,goal,plan=ready(tmp_path)
    task=db.add_task("할 일","",plan)
    with pytest.raises(ValueError,match="업무"):
        db.delete_work_plan(plan)
    assert db.read_work_plan(plan)["goal_id"]==goal
    db.update_task(task,"할 일","",None)
    db.delete_work_plan(plan)
    db.delete_goal(goal)
    assert db.read_task(task)["plan_id"] is None


def test_explicit_delete_restrictions_and_audit_cascade(tmp_path):
    db,_,plan=ready(tmp_path)
    task=db.add_task("진행 업무","",plan)
    db.set_task_status(task,"in_progress")
    with pytest.raises(ValueError,match="삭제"):
        db.delete_task(task)
    db.set_task_status(task,"done")
    with pytest.raises(ValueError):
        db.delete_task(task)
    db.set_task_status(task,"todo")
    db.set_task_status(task,"cancelled")
    db.delete_task(task)
    with pytest.raises(ValueError):
        db.read_task(task)
    with sqlite3.connect(db.path) as con:
        assert con.execute("SELECT COUNT(*) FROM company_task_status_events WHERE task_id=?",(task,)).fetchone()[0]==0
    db.delete_work_plan(plan)


def test_permissions_require_login_for_every_method(tmp_path):
    db,_,plan=ready(tmp_path)
    task=db.add_task("보호", "", plan)
    db.logout()
    actions=(lambda:db.add_task("불법"),lambda:db.read_task(task),
             lambda:db.list_tasks(),lambda:db.update_task(task,"불법"),
             lambda:db.set_task_status(task,"blocked"),
             lambda:db.list_task_status_events(task),lambda:db.delete_task(task))
    for action in actions:
        with pytest.raises(AuthenticationError):
            action()
    assert LocalStore(db.path).health()["status"]=="ok"
    db.login(USER,PASSWORD)
    assert db.read_task(task)["status"]=="todo"


def test_atomic_status_transition_rolls_back_on_audit_failure(tmp_path):
    db,_,_=ready(tmp_path)
    task=db.add_task("감사 롤백")
    with sqlite3.connect(db.path) as con:
        con.execute("""CREATE TRIGGER block_event BEFORE INSERT ON company_task_status_events
                     WHEN NEW.new_status='in_progress' BEGIN SELECT RAISE(ABORT,'rejected'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        db.set_task_status(task,"in_progress")
    assert db.read_task(task)["status"]=="todo"
    assert len(db.list_task_status_events(task))==1


def test_schema_upgrade_preserves_preexisting_notes(tmp_path):
    path=tmp_path/"old.sqlite3"
    db=LocalStore(path)
    db.setup_owner(USER,PASSWORD)
    db.save_note("이전 메모 보존")
    db.save_company("회사 기록","","운영")
    db.add_goal("기존 목표")
    db.logout()
    reopened=LocalStore(path)
    reopened.login(USER,PASSWORD)
    task=reopened.add_task("추가 업무")
    assert reopened.read_company()["name"]=="회사 기록"
    assert reopened.read_note()=="이전 메모 보존"
    assert reopened.read_task(task)["title"]=="추가 업무"


def test_invalid_task_ids_fail_closed(tmp_path):
    db,_,_=ready(tmp_path)
    for bad in (0, True, -1, "1", None):
        with pytest.raises(ValueError):
            db.read_task(bad)
        with pytest.raises(ValueError):
            db.delete_task(bad)
        with pytest.raises(ValueError):
            db.list_task_status_events(bad)
    for action in (lambda:db.read_task(500),lambda:db.update_task(500,"missing"),
                   lambda:db.set_task_status(500,"in_progress"),
                   lambda:db.list_task_status_events(500),lambda:db.delete_task(500)):
        with pytest.raises(ValueError):
            action()
