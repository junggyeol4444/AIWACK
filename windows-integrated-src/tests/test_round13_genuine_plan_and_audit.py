"""13회차 실제 코드 회귀: SQLite/모의 응답. Windows GGUF 실측이 아님."""
from __future__ import annotations
import json
import sys
import pytest
from desktop import company_wide_campaign as wide
from desktop import company_operations as ops
from desktop import company_customer_cases as cases
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig


def test_fullwidth_wrong_department_is_not_relabelled():
    prompt='Write one task for 고객지원부.\nRESPONSE:'
    with pytest.raises(ValueError,match='요청한 부서'):
        wide._parse_single_chief_completion(
            prompt+'\n재무회계부｜매출 점검｜거래 장부를 점검하고 기록을 작성한다',
            prompt,'고객지원부')


def test_fullwidth_requested_department_accepted():
    prompt='Write one task for 고객지원부.\nRESPONSE:'
    title,body=wide._parse_single_chief_completion(
        prompt+'\n고객지원부｜문의 분석｜실제 문의 내역을 분류하고 검토 보고서를 작성한다',
        prompt,'고객지원부')
    assert title=='문의 분석' and '검토 보고서' in body


def test_single_department_markdown_numbered_actual_row():
    prompt='RESPONSE:'
    title,body=wide._parse_single_chief_completion(
        prompt+'\n1. 고객지원부｜문의 분석｜실제 문의 사례를 분류하고 검토 기록을 작성한다',
        prompt,'고객지원부')
    assert title=='문의 분석' and '검토 기록' in body


def test_single_department_multiple_pipe_rows_are_rejected():
    prompt='RESPONSE:'
    text=('고객지원부|고객 분석|고객 문의를 분석하고 문서로 작성한다\n'
          '재무회계부|결제 승인|다른 부서의 거래를 승인한다')
    with pytest.raises(ValueError,match='여러 부서'):
        wide._parse_single_chief_completion(prompt+'\n'+text,prompt,'고객지원부')


def test_single_department_json_requires_exact_department_and_no_extra_text():
    prompt='RESPONSE:'
    data={'department':'고객지원부','title':'문의 분석',
          'instruction':'고객 문의를 분류하고 품질 확인 문서를 작성한다'}
    text=json.dumps(data,ensure_ascii=False)
    assert wide._parse_single_chief_completion(prompt+'\n'+text,prompt,'고객지원부')[0]=='문의 분석'
    data['department']='재무회계부'
    with pytest.raises(ValueError,match='요청한 부서'):
        wide._parse_single_chief_completion(prompt+'\n'+json.dumps(data,ensure_ascii=False),prompt,'고객지원부')
    with pytest.raises(ValueError,match='JSON 생성 결과'):
        wide._parse_single_chief_completion(prompt+'\n'+text+'\n미검증 부가 명령',prompt,'고객지원부')


def test_two_field_row_cannot_use_another_department_as_title():
    with pytest.raises(ValueError,match='요청한 부서'):
        wide._parse_single_chief_completion(
            '재무회계부|원거래 장부를 검토하고 회계 문서를 작성한다',
            'RESPONSE:','고객지원부')


def test_single_department_other_named_department_freeform_rejected():
    with pytest.raises(ValueError,match='요청한 부서'):
        wide._parse_single_chief_completion('재무회계부: 거래 자료를 점검하고 결과를 기록한다',
                                             'RESPONSE:','고객지원부')


def _office(tmp_path,monkeypatch):
    store=LocalStore(tmp_path/'round13.sqlite3')
    store.setup_owner('round13-owner','round13-test-password')
    ops.initialize_company_blueprint(store)
    model=store.add_local_model(ModelConfig('모의 모델','llamafile',sys.executable,'',64))
    for employee in store.list_employee_records():
        store.set_employee_model(employee['id'],model)
    def fake_chief(config,prompt,**kw):
        if '담당 부서: ' in prompt:
            names=prompt.rsplit('담당 부서: ',1)[1].split(', ')
            return '\n'.join(f'{name}|업무 검토|{name} 부서의 결과를 작성하고 검증한다' for name in names)
        return '총괄 모델이 직원 결과물의 품질을 검토했다'
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',fake_chief)
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**kw:'직원 모델의 문서 검토 결과')
    return store


def test_campaign_reused_chief_call_is_not_two_verified_reviews(tmp_path,monkeypatch):
    store=_office(tmp_path,monkeypatch)
    source=ops.create_task(store,'전체 협업 원본','부서별 결과를 검토한다')
    campaign=wide.approve(store,wide.propose(store,source)['id'])
    reports=[]
    for i in range(2):
        result=wide.run_next(store,campaign['id'])['work']
        store.review_task_artifact(result['artifact_id'],'approved')
        store.review_chief_task_report(result['report_id'],'accepted')
        ops.finalize_approved_artifact(store,result['artifact_id'])
        reports.append(result['report_id'])
    assert wide.verified_progress(store,campaign['id'])['verified_chief_model_call_links']==2
    with store._connect() as con:
        original=con.execute('SELECT chief_model_call_id FROM company_chief_task_reports WHERE id=?',
                             (reports[0],)).fetchone()[0]
        with pytest.raises(__import__('sqlite3').IntegrityError):
            con.execute('UPDATE company_chief_task_reports SET chief_model_call_id=? WHERE id=?',
                        (original,reports[1]))
    assert wide.verified_progress(store,campaign['id'])['verified_chief_model_call_links']==2


def test_customer_reused_chief_call_cannot_attest_two_cases(tmp_path,monkeypatch):
    store=_office(tmp_path,monkeypatch)
    ids=[]
    for i in range(2):
        case=cases.create(store,f'round13-case-{i}','고객A','제품 결과 문서 검토 요청')
        ops.assign_task(store,case['task_id'])
        ops.approve_chief_order(store,case['task_id'],'고객 문의 답변 초안을 검토하고 품질을 확인한다')
        result=ops.execute_approved_chief_cycle(store,case['task_id'])
        store.review_task_artifact(result['artifact_id'],'approved')
        store.review_chief_task_report(result['report_id'],'accepted')
        ops.finalize_approved_artifact(store,result['artifact_id'])
        cases.attach_approved_reply(store,case['id'],result['artifact_id'])
        ids.append((case['id'],result['report_id']))
    assert all(cases.read(store,i)['chief_model_call_audited'] for i,_ in ids)
    with store._connect() as con:
        call=con.execute('SELECT chief_model_call_id FROM company_chief_task_reports WHERE id=?',
                         (ids[0][1],)).fetchone()[0]
        with pytest.raises(__import__('sqlite3').IntegrityError):
            con.execute('UPDATE company_chief_task_reports SET chief_model_call_id=? WHERE id=?',
                        (call,ids[1][1]))
    assert all(cases.read(store,i)['chief_model_call_audited'] for i,_ in ids)


def test_resume_rejects_missing_chief_call_link_before_next_gguf(tmp_path,monkeypatch):
    """모의 SQLite 기록 검사만 수행하며 실제 GGUF 바이너리를 실행하지 않는다."""
    from pathlib import Path
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    from validation import windows_real_30_step_campaign_e2e as real30
    cli=tmp_path/'llama-completion.exe'
    gguf=tmp_path/'round13.gguf'
    cli.write_bytes(b'fixture-only-not-an-executable')
    gguf.write_bytes(b'GGUF'+b'fixture-only-not-a-model')
    store=LocalStore(tmp_path/'ephemeral_31_agent_campaign.sqlite3')
    store.setup_owner(real30.USER,real30.PASSWORD)
    ops.initialize_company_blueprint(store)
    model=store.add_local_model(ModelConfig('회귀 검사 모델','llama_cpp',str(cli),str(gguf),256))
    for e in store.list_employee_records():
        store.set_employee_model(e['id'],model)
    def fake(config,prompt,**kw):
        if '담당 부서: ' in prompt:
            names=prompt.rsplit('담당 부서: ',1)[1].split(', ')
            return '\n'.join(f'{name}|업무 문서|{name}의 결과를 작성하고 검증한다' for name in names)
        return '실제 실행하지 않은 모의 총괄 검토 의견'
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',fake)
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**k:'모의 직원 결과 문서')
    source=ops.create_task(store,'15부서 실제 GGUF 고객 지원 프로젝트',
                           '고객지원 정책과 문서 작성 및 품질 점검')
    campaign=wide.approve(store,wide.propose(store,source)['id'])
    work=wide.run_next(store,campaign['id'])['work']
    store.review_task_artifact(work['artifact_id'],'approved')
    store.review_chief_task_report(work['report_id'],'accepted')
    ops.finalize_approved_artifact(store,work['artifact_id'])
    assert wide.verified_progress(store,campaign['id'])['verified_chief_model_call_links']==1
    step=campaign['steps'][0]
    checkpoint={'model_backend':'real GGUF Windows','success':False,
                'campaign_id':campaign['id'],'completed_tasks':1,
                'binary_sha256':{'cli':real30._binary_sha256(cli),'gguf':real30._binary_sha256(gguf)},
                'steps':[{'ordinal':1,'employee_id':step['employee_id'],
                          'department':step['department'],'artifact_id':work['artifact_id']} ]}
    with store._connect() as con:
        con.execute('UPDATE company_chief_task_reports SET chief_model_call_id=NULL WHERE id=?',
                    (work['report_id'],))
    store.logout()
    with pytest.raises(ValueError,match='총괄 실제 모델 호출'):
        real30._resume_fixture(store,cli.resolve(),gguf.resolve(),checkpoint,
                               expected_binary_hashes=checkpoint['binary_sha256'])