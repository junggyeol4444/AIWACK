"""Real Windows GGUF full 31-agent/15-department/30-task backend acceptance.

This runs actual llama.cpp inference, never simulated model text. The test
owner is a DISPOSABLE fixture, not a real user's GUI review or consent.
No external payments, web businesses or production owner accounts.
"""
from __future__ import annotations
import hashlib,json,os,sqlite3,sys,tempfile
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'windows-integrated-src'))
from desktop import company_operations as ops
from desktop import company_wide_campaign as wide
from desktop.model_runtime import ModelConfig
from desktop.storage import LocalStore


def read_failed_chief_plan_audit(db: Path) -> list[dict]:
    """Read real-model rejection metadata without exporting prompt or output text.

    A missing table means the run stopped before model inference, not success.
    All results originate from the disposable test's read-only SQLite file.
    """
    if not db.is_file():
        return []
    uri='file:'+db.resolve().as_posix()+'?mode=ro'
    with sqlite3.connect(uri, uri=True, timeout=3) as con:
        found=con.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='aiwack_wide_chief_rejected_attempts'""").fetchone()
        if not found:
            return []
        rows=con.execute("""SELECT model_call_id,attempt_kind,requested_departments,
                    output_sha256,output_chars,error_reason
                    FROM aiwack_wide_chief_rejected_attempts ORDER BY id""").fetchall()
    result=[]
    for call_id,kind,departments,sha,chars,reason in rows:
        if kind not in ('three_departments','single_department') or len(sha)!=64:
            raise ValueError('실제 총괄 호출 실패 감사의 필수 형식이 손상됐습니다.')
        result.append({'real_model_call_id':call_id,'kind':kind,
                       'requested_departments':json.loads(departments),
                       'output_sha256':sha,'output_chars':chars,
                       'parser_failure_reason':reason})
    return result


USER='e2e_full30_fixture_owner'
PASSWORD='full-30-only-temporary-owner-password-2026'


def _binary_sha256(path:Path)->str:
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def _save_checkpoint_atomic(checkpoint:Path,report:dict)->None:
    payload=json.dumps(report,ensure_ascii=False,indent=2).encode('utf-8')
    fd,temp=tempfile.mkstemp(prefix='.aiwack-checkpoint-',suffix='.tmp',dir=checkpoint.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(payload);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,checkpoint)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def _record_rejected_resume(evidence:Path,checkpoint_file:Path,report:dict)->Path:
    """Do not mutate earlier real-GGUF checkpoint when resume verification fails."""
    rejection=dict(report)
    rejection['success']=False
    rejection['original_checkpoint_sha256']=_binary_sha256(checkpoint_file)
    destination=evidence/('resume_rejected_'+uuid4().hex+'.json')
    _save_checkpoint_atomic(destination,rejection)
    return destination


def _resume_fixture(store,cli,gguf,checkpoint,*,expected_binary_hashes=None):
    """Resume only previously persisted real inference and owner-approved tasks.

    Never manufacture an approved task, model-call ID or owner decision.
    """
    if not isinstance(checkpoint,dict):
        raise ValueError('재개 체크포인트 형식 오류')
    if expected_binary_hashes is not None and (
            not isinstance(expected_binary_hashes,dict)
            or checkpoint.get('binary_sha256')!=expected_binary_hashes):
        raise ValueError('실제 GGUF/CLI 바이너리 변경으로 재개 거부')
    count=checkpoint.get('completed_tasks')
    steps=checkpoint.get('steps')
    if (type(count) is not int or not 0<=count<=30
            or not isinstance(steps,list) or len(steps)!=count
            or ('success' in checkpoint and type(checkpoint['success']) is not bool)):
        raise ValueError('재개 체크포인트의 단계 수·성공 상태·목록 형식 오류')
    cid=checkpoint.get('campaign_id')
    if cid is not None and (type(cid) is not int or cid<=0):
        raise ValueError('협업 식별자 손상')
    if checkpoint.get('success') is True and count!=30:
        raise ValueError('성공 체크포인트와 실제 업무 수 불일치')
    store.login(USER,PASSWORD)
    employees=store.list_employee_records()
    if len(employees)!=31:
        raise ValueError('재개 대상 직원 31명 구성 불일치')
    models=store.list_local_models()
    if len(models)!=1 or models[0]['backend']!='llama_cpp' or (
           Path(models[0]['executable_path']).resolve()!=cli
           or Path(models[0]['model_path']).resolve()!=gguf):
        raise ValueError('실제 GGUF/llama.cpp 모델 설정이 변경됐습니다.')
    model_id=models[0]['id']
    for employee in employees:
        binding=store.read_employee_model(int(employee['id']))
        if not binding or binding['model_id']!=model_id:
            raise ValueError('31명 직원 중 로컬 GGUF 할당이 바뀌었습니다.')
    tasks=[t for t in store.list_tasks()
           if t['title']=='15부서 실제 GGUF 고객 지원 프로젝트']
    if len(tasks)!=1 or tasks[0]['description']!='고객지원 정책과 문서 작성 및 품질 점검':
        raise ValueError('기존 시험 업무가 변경됐습니다.')
    with store._connect() as con:
        wide.initialize(con)
        plans=con.execute('SELECT id,state FROM aiwack_wide_campaigns WHERE source_task_id=?',
                          (tasks[0]['id'],)).fetchall()
    if len(plans)>1 or any(state not in ('draft','approved') for _,state in plans):
        raise ValueError('기존 회사 전체 협업 승인 이력 이상')
    if plans and plans[0][1]=='draft':
        raise ValueError('미승인 초안을 자동 승인할 수 없습니다.')
    existing=int(plans[0][0]) if plans else None
    if existing is None:
        if count!=0 or steps or cid is not None:
            raise ValueError('기존 캠페인 없이 완료된 업무 체크포인트 존재')
        wide.staged_plan_progress(store,tasks[0]['id'])
        return tasks[0]['id'],None,0
    if existing!=cid:
        raise ValueError('체크포인트 캠페인 ID가 다릅니다.')
    plan=wide.read(store,existing)
    if len(plan['steps'])!=30 or plan['distinct_departments']!=15 or plan['distinct_worker_roles']!=30:
        raise ValueError('기존 15부서/30역할 구성 손상')
    progress=wide.verified_progress(store,existing)
    if (progress['verified_completed_tasks']!=count
            or progress['verified_genuine_prefix_tasks']!=count
            or progress['verified_chief_model_call_links']!=count):
        raise ValueError('기존 단계 실제 직원·총괄·관리자 승인 연결 불일치')
    with store._connect() as con:
        for index,entry in enumerate(steps):
            verified=progress['verified_evidence'][index]
            if (not isinstance(entry,dict) or entry.get('ordinal')!=index+1
                or entry.get('employee_id')!=plan['steps'][index]['employee_id']
                or entry.get('department')!=plan['steps'][index]['department']
                or entry.get('artifact_id')!=verified['artifact_id']):
                raise ValueError('이전 단계 체크포인트의 직원·결과물 연결 오류')
            worker_call,chief_call=entry.get('worker_call_id'),entry.get('chief_call_id')
            if (type(worker_call) is not int or type(chief_call) is not int
                    or worker_call<=0 or chief_call<=worker_call):
                raise ValueError('실제 모델 호출 ID가 기록되지 않았습니다.')
            calls=con.execute('''SELECT id,employee_id,model_id,status,output_chars
                FROM ai_model_call_history WHERE id IN (?,?) ORDER BY id''',
                (worker_call,chief_call)).fetchall()
            if (len(calls)!=2 or [c[0] for c in calls]!=[worker_call,chief_call]
                 or [c[1] for c in calls]!=[entry['employee_id'],plan['chief_employee_id']]
                 or any(c[2]!=model_id or c[3]!='success' or c[4]<=0 for c in calls)):
                raise ValueError('과거 실제 GGUF 모델 호출 기록 불일치')
            work=con.execute('''SELECT r.model_call_id,r.task_id,r.model_id,r.status
                FROM company_task_artifacts a JOIN company_task_runs r ON r.id=a.run_id
                WHERE a.id=?''',(entry['artifact_id'],)).fetchone()
            if (work is None or work[0]!=worker_call
                  or work[1]!=plan['steps'][index]['task_id']
                  or work[2]!=model_id or work[3]!='success'):
                raise ValueError('과거 실제 모델 호출과 결과물 연결 오류')
            artifact=store.read_task_artifact(entry['artifact_id'])
            report=store.find_chief_task_report(entry['artifact_id'])
            if (not report or report.get('chief_model_call_id')!=chief_call
                or report['owner_decision']!='accepted'
                or artifact['review_status']!='approved'
                or artifact['sha256']!=entry.get('artifact_sha256')
                or report['sha256']!=entry.get('chief_report_sha256')
                or hashlib.sha256(artifact['body'].encode('utf-8')).hexdigest()!=artifact['sha256']
                or hashlib.sha256(report['body'].encode('utf-8')).hexdigest()!=report['sha256']):
                raise ValueError('과거 결과물·총괄 보고·관리자 승인의 무결성 오류')
        if count<30 and con.execute('SELECT 1 FROM company_task_runs WHERE task_id=?',
                         (plan['steps'][count]['task_id'],)).fetchone():
            raise ValueError('미완료 실행 기록이 있어 GGUF 재호출 차단')
    return tasks[0]['id'],existing,count


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
            result=wide.run_next(store,cid,require_genuine_provenance=True)
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
        report['failure_kind']=type(exc).__name__
        try:
            report['chief_plan_rejections']=read_failed_chief_plan_audit(db)
        except (sqlite3.Error,ValueError) as audit_error:
            report['chief_plan_audit_read_error']=type(audit_error).__name__
        save();raise
    finally:
        try:store.logout()
        except Exception:pass

if __name__=='__main__':
    if len(sys.argv)!=4:
        raise SystemExit('Usage: windows_real_30_step_campaign_e2e.py CLI GGUF EVIDENCE')
    verify(*(Path(p) for p in sys.argv[1:]))
    print('ACTUAL_WINDOWS_GGUF_31_MODELS_15_DEPARTMENTS_30_STEPS_BACKEND_PASS',flush=True)
