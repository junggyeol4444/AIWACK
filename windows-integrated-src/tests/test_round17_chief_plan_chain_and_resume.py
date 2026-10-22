"""17회차: 실제 총괄 생성 계획·30개 승인 단계·재개 체크포인트 보존 검사.

이 파일의 모델 출력은 모의 문자열이다. Windows EXE/GGUF 실사용 합격 증거가 아니다.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest
from desktop import company_operations as ops
from desktop import company_wide_campaign as wide
from desktop.model_runtime import ModelConfig
from desktop.storage import LocalStore


def _approved(tmp_path,monkeypatch):
    store=LocalStore(tmp_path/'round17.sqlite3')
    store.setup_owner('round17-owner','round17-password')
    ops.initialize_company_blueprint(store)
    model=store.add_local_model(ModelConfig('회귀용 모델','llamafile',sys.executable,'',32))
    for person in store.list_employee_records():
        store.set_employee_model(person['id'],model)
    def answer(config,prompt,**kwargs):
        names=prompt.rsplit('담당 부서: ',1)[1].split(', ')
        return '\n'.join(f'{name}|검증 지시|{name} 부서의 자료를 수집하고 결과물에 근거를 작성한다' for name in names)
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',answer)
    task=ops.create_task(store,'원본 기준 업무','승인된 모델 결과물 검증')
    draft=wide.propose(store,task)
    approved=wide.approve(store,draft['id'])
    return store,task,approved


def test_plan_staging_all_30_instructions_match_before_first_worker(tmp_path,monkeypatch):
    store,source,plan=_approved(tmp_path,monkeypatch)
    assert wide.verified_progress(store,plan['id'])['verified_completed_tasks']==0
    with store._connect() as con:
        wide._assert_campaign_plan_matches_genuine_staging(store,con,plan['id'])
        assert con.execute('SELECT COUNT(*) FROM aiwack_wide_campaign_steps').fetchone()[0]==30


def test_changed_source_task_refuses_verified_progress(tmp_path,monkeypatch):
    store,source,plan=_approved(tmp_path,monkeypatch)
    with store._connect() as con:
        con.execute("UPDATE company_tasks SET description='수정된 기준 업무' WHERE id=?",(source,))
    with pytest.raises(ValueError,match='기준 업무의 원본'):
        wide.verified_progress(store,plan['id'])


def test_replaced_plan_text_even_with_recomputed_digest_is_rejected(tmp_path,monkeypatch):
    store,source,plan=_approved(tmp_path,monkeypatch)
    with store._connect() as con:
        con.execute('DROP TRIGGER aiwack_wide_campaign_step_no_update')
        row=con.execute('''SELECT ordinal,department_id,employee_id,role,title,
            instruction,chief_model_call_id FROM aiwack_wide_campaign_steps
            WHERE campaign_id=? AND ordinal=1''',(plan['id'],)).fetchone()
        changed='조작된 실행 지시: 관리자 승인 없는 외부 동작'
        digest=wide._step_digest(plan['id'],row[0],row[1],row[2],row[3],row[4],changed,row[6])
        con.execute('''UPDATE aiwack_wide_campaign_steps SET instruction=?,plan_sha256=?
            WHERE campaign_id=? AND ordinal=1''',(changed,digest,plan['id']))
    with pytest.raises(ValueError,match='생성 원문'):
        wide.verified_progress(store,plan['id'])


def test_replaced_chief_call_even_with_recomputed_digest_is_rejected(tmp_path,monkeypatch):
    store,source,plan=_approved(tmp_path,monkeypatch)
    with store._connect() as con:
        con.execute('DROP TRIGGER aiwack_wide_campaign_step_no_update')
        row=con.execute('''SELECT ordinal,department_id,employee_id,role,title,
            instruction,chief_model_call_id FROM aiwack_wide_campaign_steps
            WHERE campaign_id=? AND ordinal=1''',(plan['id'],)).fetchone()
        other=con.execute('''SELECT chief_model_call_id FROM aiwack_wide_campaign_steps
            WHERE campaign_id=? AND ordinal=7''',(plan['id'],)).fetchone()[0]
        digest=wide._step_digest(plan['id'],*row[:6],other)
        con.execute('''UPDATE aiwack_wide_campaign_steps
            SET chief_model_call_id=?,plan_sha256=? WHERE campaign_id=? AND ordinal=1''',
            (other,digest,plan['id']))
    with pytest.raises(ValueError,match='생성 원문'):
        wide.verified_progress(store,plan['id'])


def test_resume_checkpoint_bad_schema_rejected_before_login(tmp_path):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    from validation import windows_real_30_step_campaign_e2e as e2e
    class NoLogin:
        def login(self,*args,**kwargs):
            pytest.fail('손상된 체크포인트는 로그인·DB 변경 전에 거부해야 함')
    bad=[{'completed_tasks':True,'steps':[],'success':False},
         {'completed_tasks':-1,'steps':[],'success':False},
         {'completed_tasks':31,'steps':[],'success':False},
         {'completed_tasks':0,'steps':{},'success':False},
         {'completed_tasks':0,'steps':[],'success':'false'},
         {'completed_tasks':0,'steps':[],'success':False,'campaign_id':'123'}]
    for record in bad:
        with pytest.raises(ValueError,match='체크포인트'):
            e2e._resume_fixture(NoLogin(),Path('fake.exe'),Path('fake.gguf'),record)


def _approved_customer_reply(tmp_path,monkeypatch):
    from desktop import company_customer_cases as cases
    store=LocalStore(tmp_path/'round17_customer.sqlite3')
    store.setup_owner('round17-customer','round17-customer-password')
    ops.initialize_company_blueprint(store)
    model=store.add_local_model(ModelConfig('고객지원 회귀 모델','llamafile',sys.executable,'',32))
    for person in store.list_employee_records():
        store.set_employee_model(person['id'],model)
    case=cases.create(store,'round17-case','고객별칭','제품 설명 문서의 오류를 확인해주세요')
    ops.assign_task(store,case['task_id'])
    ops.approve_chief_order(store,case['task_id'],'문서 오류 원인과 승인된 답변 작성')
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**kw:'고객지원 담당자의 문서 오류 수정 안내')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',lambda *a,**kw:'총괄 AI의 문서 오류 확인 보고서')
    result=ops.execute_approved_chief_cycle(store,case['task_id'])
    store.review_task_artifact(result['artifact_id'],'approved')
    store.review_chief_task_report(result['report_id'],'accepted')
    ops.finalize_approved_artifact(store,result['artifact_id'])
    cases.attach_approved_reply(store,case['id'],result['artifact_id'])
    return store,case


def test_customer_reply_atomic_export_and_restart(tmp_path,monkeypatch):
    from desktop import company_customer_cases as cases
    store,case=_approved_customer_reply(tmp_path,monkeypatch)
    exported=cases.export_approved_reply(store,case['id'])
    path=Path(exported['path'])
    assert path.exists()
    assert not list(path.parent.glob('.*.tmp'))
    store.logout()
    reopened=LocalStore(store.path)
    reopened.login('round17-customer','round17-customer-password')
    assert cases.read_export(reopened,exported['id'])['file_sha256']==exported['file_sha256']
    assert cases.read_export(reopened,exported['id'])['actual_customer_reply_sent'] is False


def test_customer_reply_failed_atomic_publish_rolls_back_sqlite(tmp_path,monkeypatch):
    from desktop import company_customer_cases as cases
    import os
    store,case=_approved_customer_reply(tmp_path,monkeypatch)
    def fail_rename(src,dst):
        raise OSError('테스트 전용 파일 게시 실패')
    monkeypatch.setattr(os,'replace',fail_rename)
    with pytest.raises(OSError,match='파일 게시 실패'):
        cases.export_approved_reply(store,case['id'])
    with store._connect() as con:
        cases._init_reply_exports(con)
        assert con.execute('SELECT COUNT(*) FROM aiwack_customer_reply_exports').fetchone()[0]==0
    folder=Path(store.path).parent/'aiwack_customer_reply_documents'
    assert list(folder.glob('*'))==[]
    assert list(folder.glob('.*.tmp'))==[]