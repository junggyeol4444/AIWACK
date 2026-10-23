"""실GGUF 30업무 실패 시 실제 모델을 새 프롬프트로 재호출하는 SQLite 회귀.

테스트의 문자 응답은 모형이며 Windows·GGUF 실제 합격 증빙이 아니다.
"""
import sys

from desktop import company_wide_campaign as wide
from desktop.company_operations import initialize_company_blueprint, create_task
from desktop.model_runtime import ModelConfig
from desktop.storage import LocalStore


def test_first_single_failure_gets_different_real_call_prompt_and_immutable_audit(tmp_path, monkeypatch):
    db=LocalStore(tmp_path/'retry.sqlite3')
    db.setup_owner('owner','retry-check-password-2026')
    initialize_company_blueprint(db)
    model=db.add_local_model(ModelConfig('retry-test','llamafile',sys.executable,'',32))
    for person in db.list_employee_records():
        db.set_employee_model(person['id'],model)
    source=create_task(db,'사내 도구 품질 확인','고객 정보 사용 없이 검증')
    seen=[]
    def generated(config,prompt,**kwargs):
        seen.append(prompt)
        if '담당 부서:' in prompt:
            return 'not a 3 department plan'
        if '출력 형식:' in prompt:
            return 'invalid'
        # These are fixture strings, not real model inferences.
        return '관리자 승인 전 안전한 내부 자료 점검 항목을 수집하고 검토합니다.'
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',generated)
    plan=wide.propose(db,source)
    assert plan['state']=='draft' and len(plan['steps'])==30
    assert any('14자 이상' in p for p in seen)
    assert len(seen)==3*5 + 2*15
    with db._connect() as con:
        rejected=con.execute('SELECT COUNT(*) FROM aiwack_wide_chief_rejected_attempts').fetchone()[0]
        good=con.execute('SELECT COUNT(*) FROM aiwack_wide_chief_plan_attempts WHERE parsed=1').fetchone()[0]
    assert rejected==3*5+15 and good==15
    assert len(db.list_tasks()) == 1  # 관리자 승인이 없으면 업무 생성 금지


def test_single_real_chief_korean_labelled_fields_preserve_requested_department():
    name=wide.BLUEPRINT_DEPARTMENTS[0][0]
    raw=f'부서: {name}\n제목: 내부 운영 자료 점검\n작업 지시: 승인된 내부 문서를 확인하고 담당 부서의 개선 항목을 정리합니다.'
    title,instruction=wide._parse_single_chief_completion(raw,'다른 원본 질문',name)
    assert title=='내부 운영 자료 점검'
    assert instruction.startswith('승인된 내부 문서를')


def test_single_real_chief_labelled_wrong_department_or_mixed_output_rejected():
    import pytest
    name=wide.BLUEPRINT_DEPARTMENTS[0][0]
    other=wide.BLUEPRINT_DEPARTMENTS[1][0]
    invalid=[
        f'부서: {other}\n제목: 내부 점검\n작업 지시: 승인된 내부 문서의 품질 점검 항목을 정리합니다.',
        '제목: 내부 점검\n작업 지시: 승인된 내부 문서의 품질 점검 항목을 정리합니다.\n추가 자유 텍스트',
        '제목: 내부 점검\n제목: 중복 점검\n작업 지시: 승인된 내부 문서의 품질 점검 항목을 정리합니다.',
        '부서: '+name+'\n작업 지시: 승인된 내부 문서의 품질 점검 항목을 정리합니다.',
    ]
    for raw in invalid:
        with pytest.raises(ValueError):
            wide._parse_single_chief_completion(raw,'원본 질문',name)
