"""16회차: 승인 체인과 Windows HWND/PID 재탐색의 구조적 회귀.

여기서 사용하는 모델 응답은 테스트 대역이다. 실제 GGUF/Windows EXE
실행이나 T01~T20 최종 합격으로 취급하지 않는다.
"""
from __future__ import annotations

import ast
import sys
import types
from pathlib import Path

import pytest
from desktop import company_operations as ops
from desktop import company_wide_campaign as wide
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig


def _office(tmp_path, monkeypatch):
    store=LocalStore(tmp_path/'round16.sqlite3')
    store.setup_owner('round16-owner','round16-password')
    ops.initialize_company_blueprint(store)
    model=store.add_local_model(ModelConfig('테스트 전용 모의 모델','llamafile',sys.executable,'',32))
    for person in store.list_employee_records():
        store.set_employee_model(person['id'],model)

    def plan_answer(config,prompt,**kw):
        names=prompt.rsplit('담당 부서: ',1)[1].split(', ')
        return '\n'.join(f'{name}|승인 업무 검토|{name} 부서의 보고서를 작성하고 검증한다' for name in names)
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',plan_answer)
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**kw:'직원 결과물 모의 문자열')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**kw:'총괄 보고서 모의 문자열')
    source=ops.create_task(store,'15부서 검증 대상 업무','기존 승인 체인 무결성 확인')
    plan=wide.approve(store,wide.propose(store,source)['id'])
    return store,plan


def _finish_one(store,plan):
    result=wide.run_next(store,plan['id'])['work']
    store.review_task_artifact(result['artifact_id'],'approved')
    store.review_chief_task_report(result['report_id'],'accepted')
    ops.finalize_approved_artifact(store,result['artifact_id'])
    return result


def test_native_gui_refuses_second_step_without_genuine_chief_call(tmp_path,monkeypatch):
    store,plan=_office(tmp_path,monkeypatch)
    _finish_one(store,plan)
    progress=wide.verified_progress(store,plan['id'])
    assert progress['verified_completed_tasks']==1
    assert progress['verified_genuine_prefix_tasks']==0
    with pytest.raises(ValueError,match='총괄 실제 모델 호출'):
        store.run_full_company_next(plan['id'])
    assert store.list_task_runs(plan['steps'][1]['task_id'])==[]


def test_real_backend_strict_path_accepts_audited_chief_then_blocks_tampering(tmp_path,monkeypatch):
    store,plan=_office(tmp_path,monkeypatch)
    first=_finish_one(store,plan)
    chief=plan['chief_employee_id']
    call_id,_=store.begin_employee_model_call(chief,'총괄 보고 감사 테스트',required_tier='ceo')
    store.finish_employee_model_call(call_id,'success',output_chars=21,duration_ms=1)
    with store._connect() as con:
        con.execute('UPDATE company_chief_task_reports SET chief_model_call_id=? WHERE id=?',
                    (call_id,first['report_id']))
    assert wide.verified_progress(store,plan['id'])['verified_genuine_prefix_tasks']==1
    # Direct model invocation is not run by this structural test; the next
    # step may be reached only after a verified chief call audit is present.
    result=store.run_full_company_next(plan['id'])
    assert result['step']==2
    with store._connect() as con:
        con.execute("UPDATE ai_model_call_history SET output_chars=0 WHERE id=?",(call_id,))
    assert wide.verified_progress(store,plan['id'])['verified_genuine_prefix_tasks']==0
    with pytest.raises(ValueError,match='총괄 실제 모델 호출'):
        store.run_full_company_next(plan['id'])


def test_missing_chief_audit_does_not_crash_progress(tmp_path,monkeypatch):
    store,plan=_office(tmp_path,monkeypatch)
    _finish_one(store,plan)
    with store._connect() as con:
        row=con.execute('SELECT chief_employee_id FROM aiwack_wide_campaigns WHERE id=?',
                        (plan['id'],)).fetchone()
        assert row is not None
        assert wide._verified_chief_model_call_link(con,plan['id'],1,expected_chief=row[0]) is False
    assert wide.verified_progress(store,plan['id'])['verified_genuine_prefix_tasks']==0


def _native_test_functions():
    """Load only GUI helpers: no pyautogui display or Windows EXE on Linux."""
    path=Path(__file__).resolve().parents[2]/'validation/windows_packaged_real_gguf_queue_e2e.py'
    source=ast.parse(path.read_text(encoding='utf-8'))
    names={'_visible_window','find_dialog'}
    nodes=[n for n in source.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
           and n.name in names]
    code=compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec')
    state={'WINDOW_TITLES':{},'WINDOW_PIDS':{},'os':types.SimpleNamespace(name='nt'),
           'time':types.SimpleNamespace(sleep=lambda _:None,monotonic=lambda :0),
           'evidence':lambda stage:None}
    exec(code,state)
    return state


def test_recreated_same_title_other_process_is_never_clicked():
    state=_native_test_functions()
    class Window:
        title='AIWACK | 로컬 AI 모델 연결'
        width=700;height=500;left=100;top=100
        def __init__(self,hwnd):self._hWnd=hwnd
    original=Window(11)
    wrong_process=Window(12)
    state['WINDOW_TITLES'][11]=original.title
    state['WINDOW_PIDS'][original.title]=111
    state['_native_window_pid']=lambda hwnd:{11:111,12:222}[hwnd]
    state['pygetwindow']=types.SimpleNamespace(getAllWindows=lambda:[wrong_process])
    with pytest.raises(AssertionError,match='Expected one live native window'):
        state['_visible_window'](original)


def test_recreated_same_title_same_process_is_allowed():
    state=_native_test_functions()
    class Window:
        title='AIWACK | 로컬 AI 모델 연결'
        width=700;height=500;left=100;top=100
        def __init__(self,hwnd):self._hWnd=hwnd
    old=Window(11);new=Window(13)
    state['WINDOW_TITLES'][11]=old.title
    state['WINDOW_PIDS'][old.title]=111
    state['_native_window_pid']=lambda hwnd:111
    state['pygetwindow']=types.SimpleNamespace(getAllWindows=lambda:[new])
    assert state['_visible_window'](old)._hWnd==13


def test_thirty_structural_approvals_cannot_claim_genuine_completion(tmp_path,monkeypatch):
    store,plan=_office(tmp_path,monkeypatch)
    for _ in range(30):
        _finish_one(store,plan)
    structural=wide.verified_progress(store,plan['id'])
    assert structural['all_30_tasks_evidence_verified'] is True
    assert structural['verified_genuine_prefix_tasks']==0
    assert structural['all_30_chief_model_call_links_verified'] is False
    with pytest.raises(ValueError,match='30개 총괄 실제 모델 호출'):
        store.run_full_company_next(plan['id'])


def test_real_windows_30_step_script_opts_into_strict_provenance():
    path=Path(__file__).resolve().parents[2]/'validation/windows_real_30_step_campaign_e2e.py'
    source=path.read_text(encoding='utf-8')
    assert 'wide.run_next(store,cid,require_genuine_provenance=True)' in source