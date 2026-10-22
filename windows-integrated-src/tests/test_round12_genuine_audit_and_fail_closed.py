"""12회차: 진짜 모델 호출 감사 연결과 비요청 부서 계획 거부.

이 검사는 구조·SQLite 경로용 모의 출력이다. Windows GGUF 실추론 증거가 아니다.
"""
from __future__ import annotations
import sys
import pytest
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig
from desktop import company_operations as ops
from desktop import company_wide_campaign as wide


def test_three_department_parser_rejects_unrequested_extra_rows():
    group=[(1,'시장조사부',2,3),(2,'상품기획부',4,5),(3,'고객지원부',6,7)]
    raw='\n'.join(f'{name}|현황 조사|{name}에서 보고서를 작성하고 검증한다' for _,name,_,_ in group)
    assert len(wide._parse_group(raw,group))==3
    with pytest.raises(ValueError,match='요청하지 않은 부서'):
        wide._parse_group(raw+'\n존재하지않는부서|임의 업무|다른 부서 지시가 끼어 있음',group)
    # Explicit Markdown table header is not a fourth generated plan.
    assert len(wide._parse_group('| 부서명 | 작업 제목 | 작업 지시 |\n| --- | --- | --- |\n'+raw,group))==3


def test_genuine_chief_link_audit_is_separate_from_structural_mock(tmp_path,monkeypatch):
    st=LocalStore(tmp_path/'round12.sqlite3')
    st.setup_owner('round12-owner','round12-owner-password')
    ops.initialize_company_blueprint(st)
    model=st.add_local_model(ModelConfig('회귀 모의 모델','llamafile',sys.executable,'',32))
    for employee in st.list_employee_records():
        st.set_employee_model(employee['id'],model)
    def fake_plan(config,prompt,**kwargs):
        names=prompt.rsplit('담당 부서: ',1)[1].split(', ')
        return '\n'.join(f'{name}|문서 작성|{name} 부서의 업무 검토 결과물을 작성하고 검증한다' for name in names)
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',fake_plan)
    source=ops.create_task(st,'고객지원 업무 총괄 검토','부서 협업')
    campaign=wide.approve(st,wide.propose(st,source)['id'])
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**k:'직원 검토 결과물')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',lambda *a,**k:'총괄 검토 결과')
    work=wide.run_next(st,campaign['id'])['work']
    st.review_task_artifact(work['artifact_id'],'approved')
    st.review_chief_task_report(work['report_id'],'accepted')
    ops.finalize_approved_artifact(st,work['artifact_id'])
    initial=wide.verified_progress(st,campaign['id'])
    assert initial['verified_completed_tasks']==1
    assert initial['verified_chief_model_call_links']==0
    assert not initial['all_30_chief_model_call_links_verified']
    chief=campaign['chief_employee_id']
    call_id,_=st.begin_employee_model_call(chief,'총괄 검토 모의 호출',required_tier='ceo')
    st.finish_employee_model_call(call_id,'success',output_chars=12,duration_ms=2)
    with st._connect() as con:
        con.execute('UPDATE company_chief_task_reports SET chief_model_call_id=? WHERE id=?',
                    (call_id,work['report_id']))
    progress=wide.verified_progress(st,campaign['id'])
    assert progress['verified_chief_model_call_links']==1
    assert progress['actual_gguf_binary_verified'] is False
    # Wrong employee call is not a valid chief provenance link.
    with st._connect() as con:
        worker_call=con.execute('''SELECT r.model_call_id FROM company_task_runs r
             JOIN company_task_artifacts a ON a.run_id=r.id WHERE a.id=?''',
             (work['artifact_id'],)).fetchone()[0]
        con.execute('UPDATE company_chief_task_reports SET chief_model_call_id=? WHERE id=?',
                    (worker_call,work['report_id']))
    assert wide.verified_progress(st,campaign['id'])['verified_chief_model_call_links']==0


def test_single_department_real_output_rejects_wrong_department():
    prompt='Write one task for 고객지원부.\nRESPONSE:'
    with pytest.raises(ValueError,match='요청한 부서'):
        wide._parse_single_chief_completion(
            prompt+'\n재무회계부|지출 분석|실제 지출 자료를 분석하고 검증 결과를 작성한다',
            prompt,'고객지원부')
    title,body=wide._parse_single_chief_completion(
        prompt+'\n고객지원부|문의 분석|실제 고객 문의 결과를 분석하고 검증 결과를 작성한다',
        prompt,'고객지원부')
    assert title=='문의 분석' and '고객 문의' in body


def test_customer_reply_local_export_reports_chief_audit_truthfully(tmp_path,monkeypatch):
    from desktop import company_customer_cases as cases
    st=LocalStore(tmp_path/'round12_support.sqlite3')
    st.setup_owner('round12-support','round12-support-password')
    ops.initialize_company_blueprint(st)
    model=st.add_local_model(ModelConfig('고객지원 회귀 모의','llamafile',sys.executable,'',32))
    for e in st.list_employee_records():
        st.set_employee_model(e['id'],model)
    case=cases.create(st,'support-case-001','고객A','문서 내용이 잘못 표시됩니다')
    route=ops.assign_task(st,case['task_id'])
    ops.approve_chief_order(st,case['task_id'],'문의 답변 초안 작성과 근거 검증')
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**k:'고객지원 안내 초안과 해결 방법')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',lambda *a,**k:'총괄 검토 완료, 발송은 관리자 판단')
    result=ops.execute_approved_chief_cycle(st,case['task_id'])
    st.review_task_artifact(result['artifact_id'],'approved')
    st.review_chief_task_report(result['report_id'],'accepted')
    ops.finalize_approved_artifact(st,result['artifact_id'])
    reply=cases.attach_approved_reply(st,case['id'],result['artifact_id'])
    assert reply['chief_model_call_audited'] is False
    assert reply['actual_customer_reply_sent'] is False
    assert reply['actual_gguf_binary_verified'] is False
    export=cases.export_approved_reply(st,case['id'])
    assert export['external_message_delivered'] is False
    assert '고객지원 안내 초안' in __import__('pathlib').Path(export['path']).read_text(encoding='utf-8')
    st.logout()
    fresh=LocalStore(st.path);fresh.login('round12-support','round12-support-password')
    assert cases.read(fresh,case['id'])['chief_model_call_audited'] is False
    assert cases.read_export(fresh,export['id'])['file_sha256']==export['file_sha256']