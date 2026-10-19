"""Stage 11 company profile and operating-goal integration tests."""
import sqlite3
import pytest
from desktop.storage import AuthenticationError, LocalStore

OWNER = "owner_demo"
PASSWORD = "very-long-development-password-11"


def logged_in(path):
    store = LocalStore(path)
    store.setup_owner(OWNER, PASSWORD)
    return store


def test_owner_only_company_and_goal_crud(tmp_path):
    path = tmp_path / "company.sqlite3"
    store = LocalStore(path)
    with pytest.raises(AuthenticationError):
        store.read_company()
    with pytest.raises(AuthenticationError):
        store.save_company("x", "", "")
    with pytest.raises(AuthenticationError):
        store.list_goals()
    with pytest.raises(AuthenticationError):
        store.add_goal("Secret")
    with pytest.raises(AuthenticationError):
        store.update_goal(1, "x", "", "done")
    with pytest.raises(AuthenticationError):
        store.delete_goal(1)

    store.setup_owner(OWNER, PASSWORD)
    assert store.read_company()["name"] == "AI Autonomous Company"
    store.save_company("  Blue Company  ", "Initial introduction", "Ship real software")
    assert store.read_company() == {"name":"Blue Company","description":"Initial introduction","mission":"Ship real software"}
    goal_id = store.add_goal("  Launch first local app  ", "fully tested on Windows")
    assert store.list_goals() == [{"id":goal_id,"title":"Launch first local app","detail":"fully tested on Windows","status":"planned"}]
    store.update_goal(goal_id,"Launch ready EXE", "Now with persistence", "active")
    assert store.list_goals()[0]["status"] == "active"
    store.logout()
    with pytest.raises(AuthenticationError):
        store.read_company()
    with pytest.raises(AuthenticationError):
        store.delete_goal(goal_id)
    reopened = LocalStore(path)
    with pytest.raises(AuthenticationError):
        reopened.list_goals()
    reopened.login(OWNER,PASSWORD)
    assert reopened.read_company()["name"] == "Blue Company"
    assert reopened.list_goals()[0]["title"] == "Launch ready EXE"
    reopened.delete_goal(goal_id)
    assert reopened.list_goals() == []


def test_company_profile_does_not_delete_old_notes_or_owner(tmp_path):
    path = tmp_path/"old.sqlite3"
    store = logged_in(path)
    store.save_note("existing-important-note")
    store.save_company("Trusted Inc", "A company", "Build systems")
    store.add_goal("first")
    restarted=LocalStore(path)
    restarted.login(OWNER,PASSWORD)
    assert restarted.read_note()=="existing-important-note"
    assert restarted.read_company()["name"]=="Trusted Inc"
    assert len(restarted.list_goals())==1
    # Re-running the table creator must be safe.
    restarted._init_schema()
    assert len(restarted.list_goals())==1


@pytest.mark.parametrize("field,value",[
    ("name",""), ("name"," "*4), ("name","X"*81),
    ("description","Z"*501),("mission","Z"*501),
])
def test_invalid_company_fields_do_not_modify_saved_profile(tmp_path,field,value):
    store=logged_in(tmp_path/"company.sqlite3")
    store.save_company("Original", "Before", "Mission")
    fields={"name":"Original","description":"Before","mission":"Mission"}
    fields[field]=value
    with pytest.raises(ValueError):
        store.save_company(**fields)
    assert store.read_company()=={"name":"Original","description":"Before","mission":"Mission"}


@pytest.mark.parametrize("title,detail", [("", ""),(" ",""),("X"*121,""),("Goal","D"*501)])
def test_invalid_goal_fields_do_not_add_goal(tmp_path,title,detail):
    store=logged_in(tmp_path/"company.sqlite3")
    with pytest.raises(ValueError):
        store.add_goal(title,detail)
    assert store.list_goals()==[]


def test_invalid_status_and_unknown_id_do_not_change_goals(tmp_path):
    store=logged_in(tmp_path/"company.sqlite3")
    goal=store.add_goal("safe goal")
    for id_ in [0,-1,True, "1"]:
        with pytest.raises(ValueError):
            store.delete_goal(id_)
    with pytest.raises(ValueError):
        store.update_goal(goal,"injected","", "invalid")
    with pytest.raises(ValueError):
        store.update_goal(999,"not exist","","active")
    with pytest.raises(ValueError):
        store.delete_goal(999)
    assert store.list_goals()[0]["title"]=="safe goal"


def test_sql_parameterization_on_company_text(tmp_path):
    store=logged_in(tmp_path/"company.sqlite3")
    value="test'); DROP TABLE owner_accounts; --"
    store.save_company(value,"SQL?", "hello")
    goal=store.add_goal(value,value)
    assert store.read_company()["name"]==value
    assert store.list_goals()[0]["title"]==value
    store.logout()
    store.login(OWNER,PASSWORD)
    assert store.has_owner()
    with sqlite3.connect(tmp_path/"company.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM owner_accounts").fetchone()[0]==1
