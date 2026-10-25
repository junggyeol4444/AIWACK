"""실제 총괄 호출 감사와 단일 부서 임시 결과의 중단·재개 계약.

단위 테스트에서는 응답 문자열만 모의한다. 실제 GGUF/Windows EXE 합격 증빙이 아니다.
코드 작성 후 전체 개발 완료 단계의 통합 검증에서 실행한다.
"""
from __future__ import annotations

import sqlite3
import sys

import pytest

from desktop import company_operations as ops
from desktop import company_wide_campaign as wide
from desktop.model_runtime import ModelConfig
from desktop.storage import LocalStore


def _office(tmp_path):
    store = LocalStore(tmp_path / 'partial_chief_plan.sqlite3')
    store.setup_owner('partial-owner', 'partial-owner-password-2026')
    ops.initialize_company_blueprint(store)
    model = store.add_local_model(ModelConfig(
        '구조 회귀 응답용 모델', 'llamafile', sys.executable, '', 32))
    for employee in store.list_employee_records():
        store.set_employee_model(employee['id'], model)
    source = ops.create_task(store, '전체 부서 분석과 로컬 보고',
                             '관리자 승인 전에는 외부 거래를 실행하지 않음')
    return store, source


def _genuine_shape_for_group(prompt):
    names = prompt.rsplit('담당 부서: ', 1)[1].split(', ')
    return '\n'.join(
        f'{name}|업무 분석|{name} 부서의 승인 자료를 작성하고 원본 결과를 검증한다'
        for name in names)


def test_partial_real_call_contract_survives_restart_without_reinvoking_successes(
        tmp_path, monkeypatch):
    store, source = _office(tmp_path)
    names = [name for name, _ in ops.BLUEPRINT_DEPARTMENTS][:3]
    successful_single = []
    def partial_run(config, prompt, **kwargs):
        if '담당 부서: ' in prompt:
            return '형식에 맞지 않는 실제 응답'
        for name in names:
            if name in prompt:
                if name == names[2]:
                    return '짧음'
                successful_single.append(name)
                return f'{name}|기록 작성|{name} 부서의 자료를 확인하고 승인된 보고서를 작성한다'
        return '짧음'
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model', partial_run)
    with pytest.raises(ValueError, match='재계획도 실패'):
        wide.propose(store, source)
    assert successful_single == names[:2]
    partial = wide.staged_plan_progress(store, source)
    assert partial['completed_groups'] == 0
    assert partial['verified_partial_department_count'] == 2
    assert partial['partially_completed_groups'][0]['verified_single_departments'] == names[:2]
    with store._connect() as con:
        original = dict(con.execute(
            'SELECT department_name,model_call_id FROM aiwack_wide_single_department_staging'))
    store.logout()
    store = LocalStore(store.path)
    store.login('partial-owner', 'partial-owner-password-2026')
    later_calls = []
    def resumed(config, prompt, **kwargs):
        later_calls.append(prompt)
        if '담당 부서: ' in prompt:
            return _genuine_shape_for_group(prompt)
        if names[2] in prompt:
            return f'{names[2]}|기록 작성|{names[2]} 부서의 자료를 확인하고 승인된 보고서를 작성한다'
        pytest.fail('이미 검증된 단일 부서 계획을 다시 호출했습니다.')
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model', resumed)
    plan = wide.propose(store, source)
    assert plan['state'] == 'draft' and len(plan['steps']) == 30
    assert len(later_calls) == 5  # one missing single + four complete genuine groups
    with store._connect() as con:
        after = dict(con.execute(
            'SELECT department_name,model_call_id FROM aiwack_wide_single_department_staging'))
        assert con.execute('SELECT COUNT(*) FROM aiwack_wide_chief_group_staging').fetchone()[0] == 5
        assert con.execute('SELECT COUNT(*) FROM aiwack_wide_campaigns').fetchone()[0] == 1
    assert all(after[name] == original[name] for name in names[:2])


def test_single_department_checkpoint_is_immutable_and_original_bound(tmp_path, monkeypatch):
    store, source = _office(tmp_path)
    names = [name for name, _ in ops.BLUEPRINT_DEPARTMENTS][:3]
    def interrupted(config, prompt, **kwargs):
        if '담당 부서: ' in prompt:
            return '잘못된 응답'
        if names[0] in prompt:
            return f'{names[0]}|기록 작성|{names[0]} 부서의 승인 기록을 확인하고 보고서를 작성한다'
        return '짧음'
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model', interrupted)
    with pytest.raises(ValueError):
        wide.propose(store, source)
    with store._connect() as con:
        assert con.execute('SELECT COUNT(*) FROM aiwack_wide_single_department_staging').fetchone()[0] == 1
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('UPDATE aiwack_wide_single_department_staging SET title=?', ('바꾼 제목',))
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM aiwack_wide_single_department_staging')
        con.execute('UPDATE company_tasks SET description=? WHERE id=?',
                    ('기준 업무 내용이 변경됨', source))
    with pytest.raises(ValueError, match='원본 업무'):
        wide.staged_plan_progress(store, source)
