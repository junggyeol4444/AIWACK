"""Real Windows GGUF full 31-agent/15-department/30-task backend acceptance.

This runs actual llama.cpp inference, never simulated model text. The test
owner is a DISPOSABLE fixture, not a real user's GUI review or consent.
No external payments, web businesses or production owner accounts.
"""
from __future__ import annotations
import hashlib,json,os,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'windows-integrated-src'))
from desktop import company_operations as ops
from desktop import company_wide_campaign as wide
from desktop.model_runtime import ModelConfig
from desktop.storage import LocalStore

USER='e2e_full30_fixture_owner'
PASSWORD='full-30-only-temporary-owner-password-2026'

def verify(cli:Path,gguf:Path,evidence:Path):
    if os.name!='nt':raise OSError('Real Windows GGUF backend only')
    cli=cli.resolve(strict=True);gguf=gguf.resolve(strict=True)
    if cli.name.lower() not in ('llama-cli.exe','llama-completion.exe'):
        raise ValueError('Official preflight-verified llama.cpp binary required')
    with gguf.open('rb') as stream:
        if stream.read(4)!=b'GGUF':raise ValueError('Not a genuine GGUF file')
    evidence.mkdir(parents=True,exist_ok=True)
    db=evidence/'ephemeral_31_agent_campaign.sqlite3'
    if db.exists():raise FileExistsError('Do not overwrite a previous real model audit')
    store=LocalStore(db);store.setup_owner(USER,PASSWORD)
    report={'model_backend':'real GGUF Windows','actual_model_calls':0,
            'completed_tasks':0,'tested_roles':0,'tested_departments':0,
            'physical_exe_gui_tested':False,'human_owner_reviewed':False,
            'owner_action':'automated_disposable_test_owner_only',
            'external_payment_or_revenue_tested':False,
            'success':False,'steps':[]}
    def save():
        (evidence/'full_30_genuine_gguf_checkpoint.json').write_text(
            json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    save()
    try:
        ops.initialize_company_blueprint(store)
        people=store.list_employee_records()
        if len(people)!=31:raise AssertionError('Need real 31 agent profiles')
        model=store.add_local_model(ModelConfig('Official local GGUF', 'llama_cpp',
                                               str(cli),str(gguf),256))
        for e in people:store.set_employee_model(e['id'],model)
        task=ops.create_task(store,'15부서 실제 GGUF 고객 지원 프로젝트',
                             '고객지원 정책과 문서 작성 및 품질 점검')
        # Five real chief model plans; invalid rows are rejected, not mocked.
        plan=wide.approve(store,wide.propose(store,task)['id'])
        if len(plan['steps'])!=30:raise AssertionError('Missing real chief-generated steps')
        cid=plan['id'];report['campaign_id']=cid;save()
        ids=set()
        for index in range(30):
            result=wide.run_next(store,cid)
            if result.get('step')!=index+1:raise AssertionError('Wrong 30-step order')
            aid=result['work']['artifact_id'];rid=result['work']['report_id']
            artifact=store.read_task_artifact(aid)
            chief=store.find_chief_task_report(aid)
            if (artifact['review_status']!='pending' or not str(artifact['body']).strip()
                or chief is None or chief['id']!=rid or chief['owner_decision']!='pending'):
                raise AssertionError('Real worker/chief model output not pending and nonempty')
            # Test fixture account accepts purely for database-path verification,
            # not physical GUI or human authorization.
            store.review_task_artifact(aid,'approved')
            store.review_chief_task_report(rid,'accepted')
            if ops.finalize_approved_artifact(store,aid)!=plan['steps'][index]['task_id']:
                raise AssertionError('Approved actual result did not finalize')
            evidence_now=wide.verified_progress(store,cid)
            if evidence_now['verified_completed_tasks']!=index+1:
                raise AssertionError('Integrity/approved handoff failed on real model text')
            ids.add(result['employee_id'])
            report['completed_tasks']=index+1
            report['tested_departments']=evidence_now['verified_distinct_departments']
            report['steps'].append({'ordinal':index+1,'employee_id':result['employee_id'],
               'artifact_id':aid,'department':result['department'],
               'test_owner_accepted':True})
            save()
            if index==14:
                store.logout();store=LocalStore(db);store.login(USER,PASSWORD)
                if wide.verified_progress(store,cid)['verified_completed_tasks']!=15:
                    raise AssertionError('Actual 15-step SQLite restart continuity lost')
        summary=wide.verified_progress(store,cid)
        if not summary['all_30_tasks_evidence_verified'] or len(ids)!=30 or summary['verified_distinct_departments']!=15:
            raise AssertionError('30 actual GGUF staff/15 department acceptance incomplete')
        chief=wide.read(store,cid)['chief_employee_id']
        for employee in ids | {chief}:
            calls=store.list_employee_model_calls(employee)
            if not calls or any(x['status']!='success' or x['output_chars']<=0 for x in calls):
                raise AssertionError(f'Actual model audit missing for employee {employee}')
            report['actual_model_calls']+=len(calls)
        if report['actual_model_calls']<65:raise AssertionError('Fewer than 5 chief+60 real model calls')
        with sqlite3.connect(db) as con:
            assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not con.execute('PRAGMA foreign_key_check').fetchall()
        report['tested_roles']=31;report['success']=True;save();return report
    except BaseException as exc:
        report['failed_step']=report['completed_tasks']+1
        report['failure_kind']=type(exc).__name__;save();raise
    finally:
        try:store.logout()
        except Exception:pass

if __name__=='__main__':
    if len(sys.argv)!=4:
        raise SystemExit('Usage: windows_real_30_step_campaign_e2e.py CLI GGUF EVIDENCE')
    verify(*(Path(p) for p in sys.argv[1:]))
    print('ACTUAL_WINDOWS_GGUF_31_MODELS_15_DEPARTMENTS_30_STEPS_BACKEND_PASS',flush=True)
