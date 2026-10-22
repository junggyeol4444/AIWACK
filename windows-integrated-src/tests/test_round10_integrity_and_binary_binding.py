"""10회차 신규 회귀: 합성 모델 텍스트를 사용하는 SQLite 무결성 시험.

실제 Windows GUI, EXE 또는 GGUF 실행 성공을 주장하지 않는다.
"""
from __future__ import annotations
import hashlib
import sys
import pytest
from pathlib import Path
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig
from desktop import company_operations as ops
from desktop import company_wide_campaign as wide
from desktop import company_department_collaboration as chain
from desktop import company_department_progress as progress
from test_company_department_collaboration import _office

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from validation import windows_real_30_step_campaign_e2e as real30


def test_real_plan_pipe_variants_require_three_genuine_departments():
    part=[(1,'시장조사부',2,3),(2,'상품기획부',4,5),(3,'고객지원부',6,7)]
    raw='\n'.join(f'{name}｜실제 검토｜{name}에서 조사 자료를 작성하고 품질을 확인한다'
                  for _,name,_,_ in part)
    parsed=wide._parse_group(raw,part)
    assert len(parsed)==3
    with pytest.raises(ValueError,match='누락'):
        wide._parse_group('\n'.join(raw.splitlines()[:2]),part)
    with pytest.raises(ValueError,match='누락'):
        wide._parse_group('담당 부서: 시장조사부, 상품기획부, 고객지원부',part)


def test_resume_rejects_changed_gguf_or_cli_bytes_at_same_path(tmp_path):
    gguf=tmp_path/'model.gguf';cli=tmp_path/'llama-cli.exe'
    gguf.write_bytes(b'GGUF'+b'first-model-contents')
    cli.write_bytes(b'official-binary-fixture')
    expected={'gguf':real30._binary_sha256(gguf),'cli':real30._binary_sha256(cli)}
    assert expected['gguf']==hashlib.sha256(gguf.read_bytes()).hexdigest()
    checkpoint={'binary_sha256':expected}
    # Fails before any account login or model invocation.
    store=LocalStore(tmp_path/'unused.sqlite3')
    gguf.write_bytes(b'GGUF'+b'changed-model-contents')
    changed={'gguf':real30._binary_sha256(gguf),'cli':real30._binary_sha256(cli)}
    with pytest.raises(ValueError,match='무결성'):
        real30._resume_fixture(store,cli,gguf,checkpoint,expected_binary_hashes=changed)
    cli.write_bytes(b'changed-binary')
    changed={'gguf':expected['gguf'],'cli':real30._binary_sha256(cli)}
    with pytest.raises(ValueError,match='무결성'):
        real30._resume_fixture(store,cli,gguf,checkpoint,expected_binary_hashes=changed)


def test_wide_completion_and_next_worker_reject_tampered_worker_body(tmp_path,monkeypatch):
    store=LocalStore(tmp_path/'wide.sqlite3')
    store.setup_owner('owner','wide-test-password-2026')
    ops.initialize_company_blueprint(store)
    model=store.add_local_model(ModelConfig('fixture','llamafile',sys.executable,'',32))
    for employee in store.list_employee_records():
        store.set_employee_model(employee['id'],model)
    source=ops.create_task(store,'고객지원 정책 품질 개선','승인된 직원 결과만 전달')
    def chief(config,prompt,**kwargs):
        names=prompt.rsplit('담당 부서: ',1)[1].split(', ')
        return '\n'.join(f'{name}|검증 보고|{name}에서 실제 검증 문서를 작성하고 점검한다' for name in names)
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',chief)
    campaign=wide.approve(store,wide.propose(store,source)['id'])
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**kw:'승인 전 직원의 시험 결과물')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**kw:'총괄의 시험 검수 의견')
    first=wide.run_next(store,campaign['id'])['work']
    store.review_task_artifact(first['artifact_id'],'approved')
    store.review_chief_task_report(first['report_id'],'accepted')
    with store._connect() as con:
        con.execute('UPDATE company_task_artifacts SET body=? WHERE id=?',
                    ('변조된 직원 결과',first['artifact_id']))
    with pytest.raises(ValueError,match='31 AI 협업|실제 모델'):
        ops.finalize_approved_artifact(store,first['artifact_id'])
    assert store.read_task(campaign['steps'][0]['task_id'])['status']=='in_progress'


def test_department_dependency_rejects_tampered_chief_body(tmp_path,monkeypatch):
    store,source,_=_office(tmp_path,monkeypatch)
    campaign=chain.approve(store,chain.propose(store,source)['id'])
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**kw:'직원 검증용 결과물')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**kw:'총괄 검증용 의견')
    first=progress.next_step(store,campaign['id'])
    result=progress.execute_next_step(store,campaign['id'],first['task_id'],first['employee_id'])
    store.review_task_artifact(result['artifact_id'],'approved')
    store.review_chief_task_report(result['report_id'],'accepted')
    ops.finalize_approved_artifact(store,result['artifact_id'])
    assert progress.next_step(store,campaign['id'])['ready']
    with store._connect() as con:
        con.execute('UPDATE company_chief_task_reports SET body=? WHERE id=?',
                    ('변조된 총괄 검토',result['report_id']))
    assert not progress.next_step(store,campaign['id'])['ready']
    with pytest.raises(ValueError,match='선행 부서'):
        ops.execute_approved_chief_cycle(store,campaign['steps'][1]['task_id'])


def _chief_provenance_office(tmp_path,monkeypatch):
    store=LocalStore(tmp_path/'chief_provenance.sqlite3')
    store.setup_owner('chief_owner','chief-provenance-password-2026')
    department=store.add_department('고객지원부')
    chief=store.add_employee_draft('chief','총괄 AI')
    head=store.add_employee_draft('head','고객지원 부서장',department_id=department)
    staff=store.add_employee_draft('worker','고객지원 AI',department_id=department)
    store.assign_reporting_line(chief,'ceo')
    store.assign_reporting_line(head,'department_head',chief)
    store.assign_reporting_line(staff,'staff',head)
    model=store.add_local_model(ModelConfig('local test only','llamafile',sys.executable,'',64))
    store.set_employee_model(chief,model);store.set_employee_model(staff,model)
    task=ops.create_task(store,'고객지원 결과물 검토','직원 결과와 총괄 보고 연결')
    assigned=store.auto_assign_task(task)
    assert assigned['employee_id']==staff
    ops.approve_chief_order(store,task,'고객지원 결과물을 작성하고 총괄 검토를 요청한다')
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a,**kw:'직원 시험 결과물: 고객지원 절차와 확인 사항')
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',
                        lambda *a,**kw:'총괄 시험 검토: 직원 결과의 품질을 확인했다')
    return store,task,chief,staff


def test_chief_report_binds_to_exact_real_model_call_record(tmp_path,monkeypatch):
    store,task,chief,staff=_chief_provenance_office(tmp_path,monkeypatch)
    result=ops.execute_approved_chief_cycle(store,task)
    report=store.read_chief_task_report(result['report_id'])
    assert type(report['chief_model_call_id']) is int
    with store._connect() as con:
        row=con.execute('''SELECT employee_id,status,output_chars FROM ai_model_call_history
            WHERE id=?''',(report['chief_model_call_id'],)).fetchone()
        assert row[0]==chief and row[1]=='success' and row[2]>0
        assert con.execute('SELECT COUNT(*) FROM company_chief_task_reports').fetchone()[0]==1
    reopened=LocalStore(store.path)
    reopened.login('chief_owner','chief-provenance-password-2026')
    assert reopened.read_chief_task_report(result['report_id'])['chief_model_call_id']==report['chief_model_call_id']


def test_chief_report_rejects_worker_call_substitution(tmp_path,monkeypatch):
    store,task,chief,staff=_chief_provenance_office(tmp_path,monkeypatch)
    worker=ops.execute_task(store,task)
    with store._connect() as con:
        worker_call=con.execute('SELECT model_call_id FROM company_task_runs WHERE id=?',
                                (worker['run_id'],)).fetchone()[0]
    with pytest.raises(ValueError,match='총괄 실제 모델 호출'):
        store.save_chief_task_report(worker['artifact_id'],'잘못된 모델 호출',model_call_id=worker_call)
    assert store.find_chief_task_report(worker['artifact_id']) is None