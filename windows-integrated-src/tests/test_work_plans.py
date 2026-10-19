"""Stage 22: owner-only local goal-linked plans are data, never executable tasks."""
from pathlib import Path
import sqlite3
import pytest
from desktop.storage import LocalStore, AuthenticationError

USER, PASSWORD = 'workplan_owner', 'correct-horse-2026'


def connected(tmp_path):
    db = LocalStore(tmp_path / 'aiwack.sqlite3')
    db.setup_owner(USER, PASSWORD)
    goal = db.add_goal('실제 운영 목표', '실무 분석 계획')
    return db, goal


def test_create_two_plans_and_ordered_steps(tmp_path):
    db, goal = connected(tmp_path)
    one = db.add_work_plan(goal, '시장 조사 준비', '고객 조사 계획', ['대상 선정', '요구사항 정리', '내부 검토'])
    two = db.add_work_plan(goal, '발표 계획', '', ['발표안 만들기'], 'ready')
    assert one != two
    details = db.read_work_plan(one)
    assert details['goal_id'] == goal and details['goal_title'] == '실제 운영 목표'
    assert details['steps'] == ['대상 선정', '요구사항 정리', '내부 검토']
    assert details['description'] == '고객 조사 계획' and details['status'] == 'draft'
    assert [(x['id'], x['steps_count']) for x in db.list_work_plans()] == [(one, 3), (two, 1)]
    assert [x['id'] for x in db.list_work_plans(goal)] == [one, two]


def test_edit_goal_and_plan_reopen_logout_and_permission(tmp_path):
    db, goal = connected(tmp_path)
    plan = db.add_work_plan(goal, '초안', '', ['첫 단계'])
    db.update_goal(goal, '수정된 목표', '내용', 'active')
    db.update_work_plan(plan, goal, '정식 계획', '수정된 상세', ['수정 단계 1', '수정 단계 2'], 'ready')
    assert db.read_work_plan(plan)['goal_title'] == '수정된 목표'
    db.logout()
    for op in [lambda: db.list_work_plans(), lambda: db.list_work_plans(goal),
               lambda: db.read_work_plan(plan), lambda: db.add_work_plan(goal, '무단', '', ['시도']),
               lambda: db.update_work_plan(plan, goal, '무단', '', ['시도']),
               lambda: db.delete_work_plan(plan)]:
        with pytest.raises(AuthenticationError):
            op()
    reopened = LocalStore(db.path)
    with pytest.raises(AuthenticationError):
        reopened.read_work_plan(plan)
    reopened.login(USER, PASSWORD)
    record = reopened.read_work_plan(plan)
    assert (record['title'], record['description'], record['status']) == ('정식 계획', '수정된 상세', 'ready')
    assert record['steps'] == ['수정 단계 1', '수정 단계 2']


def test_fk_restrict_goal_delete_and_cascade_plan_steps(tmp_path):
    db, goal = connected(tmp_path)
    plan = db.add_work_plan(goal, '한 개의 계획', '', ['1단계', '2단계'])
    with pytest.raises(ValueError, match='업무 계획'):
        db.delete_goal(goal)
    with sqlite3.connect(db.path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('DELETE FROM company_goals WHERE id=?', (goal,))
    db.delete_work_plan(plan)
    with sqlite3.connect(db.path) as con:
        assert con.execute('SELECT COUNT(*) FROM company_work_plan_steps WHERE plan_id=?', (plan,)).fetchone()[0] == 0
    db.delete_goal(goal)
    assert db.list_goals() == []


def test_missing_goal_or_plan_fails_without_side_effect(tmp_path):
    db, goal = connected(tmp_path)
    with pytest.raises(ValueError, match='목표'):
        db.add_work_plan(9000, '없음', '', ['한 단계'])
    with pytest.raises(ValueError, match='목표'):
        db.update_work_plan(20, 9000, '없음', '', ['단계'])
    with pytest.raises(ValueError, match='계획'):
        db.update_work_plan(100, goal, '없음', '', ['단계'])
    with pytest.raises(ValueError, match='계획'):
        db.delete_work_plan(100)
    with pytest.raises(ValueError, match='계획'):
        db.read_work_plan(100)
    assert db.list_work_plans() == []


@pytest.mark.parametrize('goal_id', [0, -1, True, '1', None])
def test_invalid_goal_id(tmp_path, goal_id):
    db, goal = connected(tmp_path)
    with pytest.raises(ValueError):
        db.add_work_plan(goal_id, '계획', '', ['하나'])


@pytest.mark.parametrize('title,description,steps,status', [
    ('', '', ['단계'], 'draft'),
    ('  ', '', ['단계'], 'draft'),
    ('X'*121, '', ['단계'], 'draft'),
    ('계획', 'y'*1001, ['단계'], 'draft'),
    ('계획', '', [], 'draft'),
    ('계획', '', [''], 'draft'),
    ('계획', '', ['x'*201], 'draft'),
    ('계획', '', ['단계']*31, 'draft'),
    ('계획', '', ['단계'], 'running'),
    ('계획', '', '문자열', 'draft'),
])
def test_reject_invalid_plan_fields(tmp_path, title, description, steps, status):
    db, goal = connected(tmp_path)
    with pytest.raises(ValueError):
        db.add_work_plan(goal, title, description, steps, status)
    assert db.list_work_plans() == []


def test_update_invalid_values_do_not_modify_existing_plan(tmp_path):
    db, goal = connected(tmp_path)
    plan = db.add_work_plan(goal, '정상', '', ['보존', '단계2'])
    with pytest.raises(ValueError):
        db.update_work_plan(plan, goal, '실패', '', ['새로 입력'], 'invalid')
    assert db.read_work_plan(plan)['steps'] == ['보존', '단계2']
    assert db.read_work_plan(plan)['title'] == '정상'


def test_atomic_update_rolls_back_if_step_insert_fails(tmp_path):
    db, goal = connected(tmp_path)
    plan = db.add_work_plan(goal, '최초 계획', '', ['원래 순서'])
    with sqlite3.connect(db.path) as con:
        con.execute('''CREATE TRIGGER reject_bad_stage22 BEFORE INSERT ON company_work_plan_steps
                       WHEN NEW.instruction='문제 항목' BEGIN SELECT RAISE(ABORT, 'test failure'); END''')
    with pytest.raises(sqlite3.IntegrityError):
        db.update_work_plan(plan, goal, '임시 수정', '', ['첫 번째', '문제 항목'], 'ready')
    assert db.read_work_plan(plan)['title'] == '최초 계획'
    assert db.read_work_plan(plan)['status'] == 'draft'
    assert db.read_work_plan(plan)['steps'] == ['원래 순서']


def test_atomic_create_rolls_back_if_step_insert_fails(tmp_path):
    db, goal = connected(tmp_path)
    with sqlite3.connect(db.path) as con:
        con.execute('''CREATE TRIGGER reject_plan_step BEFORE INSERT ON company_work_plan_steps
                       WHEN NEW.instruction='문제 항목' BEGIN SELECT RAISE(ABORT, 'test failure'); END''')
    with pytest.raises(sqlite3.IntegrityError):
        db.add_work_plan(goal, '미완료 트랜잭션', '', ['정상', '문제 항목'])
    assert db.list_work_plans() == []


def test_old_data_schema_is_preserved(tmp_path):
    path = tmp_path/'old.sqlite3'
    db = LocalStore(path)
    db.setup_owner(USER, PASSWORD)
    db.save_note('old note stays')
    db.save_company('오래된 회사', '설명', '목표')
    goal = db.add_goal('오래된 목표')
    db.logout()
    upgraded = LocalStore(path)
    upgraded.login(USER, PASSWORD)
    assert upgraded.read_note() == 'old note stays'
    assert upgraded.read_company()['name'] == '오래된 회사'
    assert upgraded.list_goals()[0]['title'] == '오래된 목표'
    assert upgraded.list_work_plans() == []
    upgraded.add_work_plan(goal, '새 업무 계획', '', ['순서 한 개'])
    assert len(upgraded.list_work_plans()) == 1
