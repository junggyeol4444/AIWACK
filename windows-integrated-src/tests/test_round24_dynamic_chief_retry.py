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
