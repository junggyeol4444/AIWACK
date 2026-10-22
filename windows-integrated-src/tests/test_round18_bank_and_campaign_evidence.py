"""18회차: 금융 원본 대사와 30업무 승인·모델 감사 파일.

테스트 거래 및 모의 모델 출력은 실제 PG/은행/Windows GGUF 증거가 아니다.
"""
from __future__ import annotations
import csv
import hashlib
import hmac
import json
import sys
from pathlib import Path
import sqlite3

import pytest
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig
from desktop import company_operations as ops
from desktop import company_payment_reconciliation as pay
from desktop import company_bank_reconciliation as bank
from desktop import company_wide_campaign as wide
from desktop import company_campaign_evidence as evidence


def payment_fixture(tmp_path):
    st=LocalStore(tmp_path/'payments.sqlite3')
    st.setup_owner('owner-round18','round18-password-strong')
    b=st.create_business(1,'실제 사업 검토','오프라인 공급자 거래 증빙 시험')
    return st,b


def make_signed(st,b,kind,tx,amount,evt):
    secret='local-fixture-secret-2026-round18'
    raw=json.dumps({'provider':'bank-test-provider','event_id':evt,
        'transaction_id':tx,'business_id':b,'event_type':kind,
        'related_transaction':'','currency':'KRW','amount_minor':amount},sort_keys=True).encode()
    event=pay.ingest(st,raw,hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest(),secret)
    pay.review(st,event['id'],'accepted','관리자가 로컬 서명 거래 기록을 확인')
    return event


def write_csv(tmp_path,records):
    filename=tmp_path/'bank_source.csv'
    with filename.open('w',encoding='utf-8',newline='') as output:
        writer=csv.DictWriter(output,fieldnames=bank.COLUMNS)
        writer.writeheader();writer.writerows(records)
    return filename


def record(b,tx,amount,ref='bank-ref-001',kind='settlement'):
    return dict(bank_reference=ref,provider='bank-test-provider',transaction_id=tx,
                business_id=b,event_type=kind,amount_minor=amount,currency='KRW')


def test_bank_csv_requires_accepted_signed_events_and_survives_relogin(tmp_path):
    st,b=payment_fixture(tmp_path)
    make_signed(st,b,'settlement','tx-bank-001',15000,'event-bank-001')
    file=write_csv(tmp_path,[record(b,'tx-bank-001',15000)])
    result=st.reconcile_owner_bank_csv(file)
    assert result['matched_signed_events']==1
    assert result['independent_bank_api_verified'] is False
    assert result['real_bank_settlement_confirmed'] is False
    st.logout()
    reopened=LocalStore(st.path)
    reopened.login('owner-round18','round18-password-strong')
    assert reopened.read_bank_reconciliation(result['batch_id'])['matched_amount_minor']==15000
    with pytest.raises(ValueError,match='이미 대사'):
        reopened.reconcile_owner_bank_csv(file)


def test_bank_csv_rejects_mismatch_atomically_and_prevents_reused_event(tmp_path):
    st,b=payment_fixture(tmp_path)
    make_signed(st,b,'settlement','tx-bank-002',30000,'event-bank-002')
    file=write_csv(tmp_path,[record(b,'tx-bank-002',30000),record(b,'not-accepted',1,'bank-ref-002')])
    with pytest.raises(ValueError,match='정확히 일치'):
        bank.import_owner_csv(st,file)
    with st._connect() as con:
        bank.initialize(con)
        assert con.execute('SELECT COUNT(*) FROM aiwack_bank_reconciliation_batches').fetchone()[0]==0
        assert con.execute('SELECT COUNT(*) FROM aiwack_bank_reconciliation_matches').fetchone()[0]==0
    write_csv(tmp_path,[record(b,'tx-bank-002',30000)])
    bank.import_owner_csv(st,file)
    file2=tmp_path/'later.csv'
    file2.write_text(file.read_text(encoding='utf-8').replace('bank-ref-001','bank-ref-099'),encoding='utf-8')
    with pytest.raises(ValueError,match='대사된 거래'):
        bank.import_owner_csv(st,file2)


def test_bank_csv_rejects_forged_numbers_and_duplicate_reference(tmp_path):
    st,b=payment_fixture(tmp_path)
    make_signed(st,b,'settlement','tx-bank-003',33000,'event-bank-003')
    bad=[record(b,'tx-bank-003','33000.0'),record(b,'tx-bank-003','=33000'),
         record(b,'tx-bank-003',44000)]
    for invalid in bad:
        file=write_csv(tmp_path,[invalid])
        with pytest.raises(ValueError):bank.import_owner_csv(st,file)
    file=write_csv(tmp_path,[record(b,'tx-bank-003',33000),
                             record(b,'tx-bank-003',33000)])
    with pytest.raises(ValueError,match='고유번호 중복'):
        bank.import_owner_csv(st,file)


def test_bank_csv_immutable_and_emergency_stop(tmp_path):
    st,b=payment_fixture(tmp_path)
    make_signed(st,b,'settlement','tx-bank-004',8000,'event-bank-004')
    file=write_csv(tmp_path,[record(b,'tx-bank-004',8000)])
    item=bank.import_owner_csv(st,file)
    with st._connect() as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('UPDATE aiwack_bank_reconciliation_matches SET amount_minor=1')
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM aiwack_bank_reconciliation_batches')
    st.emergency_stop_local(True,'검토 완료 후 일시 중지')
    other=tmp_path/'other.csv'
    other.write_bytes(file.read_bytes())
    with pytest.raises(PermissionError,match='비상정지'):
        bank.import_owner_csv(st,other)
    assert bank.read(st,item['batch_id'])['matched_signed_events']==1


def campaign_fixture(tmp_path,monkeypatch):
    st=LocalStore(tmp_path/'company.sqlite3')
    st.setup_owner('campaign-round18','round18-password-strong')
    ops.initialize_company_blueprint(st)
    m=st.add_local_model(ModelConfig('구조 시험 모델','llamafile',sys.executable,'',32))
    for person in st.list_employee_records():
        st.set_employee_model(person['id'],m)
    def chief_plan(config,prompt,**kw):
        names=prompt.rsplit('담당 부서: ',1)[1].split(', ')
        return '\n'.join(f'{n}|문서 점검|{n} 업무와 문서 내용을 검토하고 결과를 작성한다' for n in names)
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',chief_plan)
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**kw:'검증된 직원 결과물 구조 시험')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',lambda *a,**kw:'총괄 보고서 구조 시험')
    task=ops.create_task(st,'30업무 감사 기준 업무','기존 부서 결과 승인 체인')
    campaign=wide.approve(st,wide.propose(st,task)['id'])
    return st,campaign


def complete_one(st,campaign):
    run=wide.run_next(st,campaign['id'])['work']
    st.review_task_artifact(run['artifact_id'],'approved')
    st.review_chief_task_report(run['report_id'],'accepted')
    ops.finalize_approved_artifact(st,run['artifact_id'])
    chief=campaign['chief_employee_id']
    call,_=st.begin_employee_model_call(chief,'총괄 보고서 감사지표 시험',required_tier='ceo')
    st.finish_employee_model_call(call,'success',output_chars=30,duration_ms=1)
    with st._connect() as con:
        con.execute('UPDATE company_chief_task_reports SET chief_model_call_id=? WHERE id=?',
                    (call,run['report_id']))
    return run


def test_campaign_evidence_requires_real_chief_call_record_not_only_approval(tmp_path,monkeypatch):
    st,campaign=campaign_fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='아직 없습니다'):
        evidence.export(st,campaign['id'])
    complete_one(st,campaign)
    result=st.export_campaign_call_evidence(campaign['id'])
    assert result['completed_tasks']==1
    assert result['independently_verified_gguf_binary'] is False
    doc=json.loads(Path(result['filename']).read_text(encoding='utf-8'))
    assert doc['steps'][0]['worker_call_id']<doc['steps'][0]['chief_call_id']
    assert doc['independently_verified_gguf_binary'] is False
    st.logout()
    other=LocalStore(st.path);other.login('campaign-round18','round18-password-strong')
    assert other.read_campaign_call_evidence(result['id'])['sha256']==result['sha256']
    with pytest.raises(ValueError,match='이미 존재'):
        other.export_campaign_call_evidence(campaign['id'])
    with other._connect() as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM aiwack_campaign_evidence_exports')


def test_campaign_evidence_previous_snapshot_still_valid_after_next_approved_step(tmp_path,monkeypatch):
    st,campaign=campaign_fixture(tmp_path,monkeypatch)
    complete_one(st,campaign)
    old=st.export_campaign_call_evidence(campaign['id'])
    complete_one(st,campaign)
    assert st.read_campaign_call_evidence(old['id'])['completed_tasks']==1
    newer=st.export_campaign_call_evidence(campaign['id'])
    assert newer['completed_tasks']==2
    assert st.read_campaign_call_evidence(old['id'])['sha256']==old['sha256']


def test_campaign_evidence_refuses_tampered_call_and_file(tmp_path,monkeypatch):
    st,campaign=campaign_fixture(tmp_path,monkeypatch)
    complete_one(st,campaign)
    doc=st.export_campaign_call_evidence(campaign['id'])
    path=Path(doc['filename'])
    path.write_text('{"forged":true}',encoding='utf-8')
    with pytest.raises(ValueError,match='변경'):
        st.read_campaign_call_evidence(doc['id'])
    # Restore bytes, then modify the DB model audit to verify the second gate.
    expected=evidence._bytes(evidence._build(st,campaign['id']))
    path.write_bytes(expected)
    with st._connect() as con:
        chief=con.execute('SELECT chief_model_call_id FROM company_chief_task_reports').fetchone()[0]
        con.execute('UPDATE ai_model_call_history SET output_chars=0 WHERE id=?',(chief,))
    with pytest.raises(ValueError,match='총괄 실제 모델 호출'):
        st.read_campaign_call_evidence(doc['id'])