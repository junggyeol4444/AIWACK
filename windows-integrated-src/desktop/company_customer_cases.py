"""관리자 접수 고객 문의 → 기존 직원 업무 → 실제 승인된 답변의 로컬 기록.

고객/주문/외부 PG 연결의 진위를 주장하지 않는다. 사용자 직접 접수와
실제 고객에게 발송된 상태를 구분한다. 외부 발송/결제/주문 생성은 실행하지 않는다.
"""
from __future__ import annotations
import hashlib
import json
import re
import sqlite3
from desktop.stage87_90_management import stopped

REF = re.compile(r'[A-Za-z0-9._:-]{5,80}\Z')


def initialize(con: sqlite3.Connection):
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_customer_cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_ref TEXT NOT NULL UNIQUE,customer_alias TEXT NOT NULL,
        question TEXT NOT NULL,task_id INTEGER NOT NULL UNIQUE REFERENCES company_tasks(id),
        catalog_item_id INTEGER REFERENCES local_catalog_items(id),
        state TEXT NOT NULL CHECK(state IN ('open','response_ready','closed')) DEFAULT 'open',
        artifact_id INTEGER REFERENCES company_task_artifacts(id),
        reply_sha256 TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        decided_at TEXT)''')
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_customer_case_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id INTEGER NOT NULL REFERENCES aiwack_customer_cases(id),
        action TEXT NOT NULL CHECK(action IN ('created','response_ready','closed')),
        old_state TEXT NOT NULL,new_state TEXT NOT NULL,
        artifact_id INTEGER,reply_sha256 TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    for op in ('UPDATE','DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS aiwack_customer_case_event_no_{op.lower()}
        BEFORE {op} ON aiwack_customer_case_events BEGIN
        SELECT RAISE(ABORT,'고객 업무 감사 이력 수정·삭제 금지'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS aiwack_customer_case_lock
        BEFORE UPDATE ON aiwack_customer_cases
        WHEN OLD.case_ref!=NEW.case_ref OR OLD.customer_alias!=NEW.customer_alias
        OR OLD.question!=NEW.question OR OLD.task_id!=NEW.task_id
        OR OLD.catalog_item_id IS NOT NEW.catalog_item_id
        OR NOT (OLD.state='open' AND NEW.state='response_ready'
             AND NEW.artifact_id IS NOT NULL AND length(NEW.reply_sha256)=64
             OR OLD.state='response_ready' AND NEW.state='closed'
             AND OLD.artifact_id=NEW.artifact_id AND OLD.reply_sha256=NEW.reply_sha256)
        BEGIN SELECT RAISE(ABORT,'고객 문의 원문·승인 이력 변경 금지'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS aiwack_customer_case_no_delete
        BEFORE DELETE ON aiwack_customer_cases BEGIN
        SELECT RAISE(ABORT,'고객 문의 감사 삭제 금지'); END''')


def _text(v,desc,limit):
    if (not isinstance(v,str) or not 1<=len(v.strip())<=limit
            or any(ord(c)<32 or ord(c)==127 for c in v)):
        raise ValueError(desc+' 입력 길이/형식 오류')
    return v.strip()


def _event(con,case_id,action,old,new,artifact=None,digest=''):
    con.execute('''INSERT INTO aiwack_customer_case_events
      (case_id,action,old_state,new_state,artifact_id,reply_sha256)
      VALUES(?,?,?,?,?,?)''',(case_id,action,old,new,artifact,digest))


def create(store,case_ref:str,customer_alias:str,question:str,*,catalog_item_id:int|None=None)->dict:
    store.require_permission('company:manage')
    if not isinstance(case_ref,str) or not REF.fullmatch(case_ref):
        raise ValueError('고객 문의 고유 번호 형식 오류')
    alias=_text(customer_alias,'고객 식별명',100)
    summary=_text(question,'고객 문의 내용',1100)
    if catalog_item_id is not None and (type(catalog_item_id) is not int or catalog_item_id<=0):
        raise ValueError('상품 카탈로그 번호 오류')
    from desktop.product_catalog import initialize as init_catalog,get as get_catalog
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        if stopped(con):raise PermissionError('비상정지 중에는 고객 업무를 생성할 수 없습니다.')
        if catalog_item_id is not None:
            init_catalog(con)
            item=get_catalog(con,catalog_item_id)
            if item['state']=='archived':raise ValueError('보관된 상품에 문의 연결 금지')
        if con.execute('SELECT 1 FROM aiwack_customer_cases WHERE case_ref=?',(case_ref,)).fetchone():
            raise ValueError('중복된 고객 문의 번호입니다.')
        title=('고객지원 문의 '+case_ref)[:120]
        task_id=int(con.execute('INSERT INTO company_tasks(title,description) VALUES(?,?)',
                                (title,summary)).lastrowid)
        con.execute('''INSERT INTO company_task_status_events(task_id,old_status,new_status)
                       VALUES(?,NULL,'todo')''',(task_id,))
        # Route to the existing customer-support team. Owner assigns the real employee.
        dep=con.execute("SELECT id FROM company_departments WHERE name='고객지원부'").fetchone()
        if not dep:
            raise ValueError('기존 고객지원부가 없어 문의 업무를 배정할 수 없습니다.')
        con.execute('''INSERT INTO company_task_routing(task_id,department_id)
                       VALUES(?,?)''',(task_id,int(dep[0])))
        case_id=int(con.execute('''INSERT INTO aiwack_customer_cases
                 (case_ref,customer_alias,question,task_id,catalog_item_id)
                 VALUES(?,?,?,?,?)''',(case_ref,alias,summary,task_id,catalog_item_id)).lastrowid)
        _event(con,case_id,'created','', 'open')
    return read(store,case_id)


def _reply_proof(con,task_id,artifact_id):
    row=con.execute('''SELECT t.status,a.body,a.sha256,r.status,h.status,r.employee_id,
      h.employee_id,rep.body,rep.sha256,rep.owner_decision,
      ord.task_id,disp.run_id,r.id,ord.worker_employee_id,
      ord.chief_employee_id,rep.chief_employee_id,r.model_id,h.model_id,
      r.output_chars,h.output_chars
      FROM company_tasks t
      JOIN company_task_artifacts a ON a.task_id=t.id
      JOIN company_task_runs r ON r.id=a.run_id AND r.task_id=t.id
      JOIN ai_model_call_history h ON h.id=r.model_call_id
      JOIN company_chief_task_reports rep ON rep.artifact_id=a.id
      JOIN company_chief_task_orders ord ON ord.id=rep.order_id AND ord.task_id=t.id
      JOIN company_chief_task_dispatches disp ON disp.order_id=ord.id AND disp.run_id=r.id
      WHERE t.id=? AND a.id=? AND a.review_status='approved' ''',(task_id,artifact_id)).fetchone()
    if not row:raise ValueError('고객지원 업무의 승인된 직원·총괄 결과를 찾을 수 없습니다.')
    (state,body,digest,run_status,call_status,run_emp,call_emp,
     report,report_sha,decision,order_task,dispatch_run,run_id,order_worker,
     order_chief,report_chief,run_model,call_model,run_chars,call_chars)=row
    if (state!='done' or run_status!='success' or call_status!='success'
        or decision!='accepted' or run_emp!=call_emp or task_id!=order_task
        or dispatch_run!=run_id or int(order_worker)!=int(run_emp)
        or int(order_chief)!=int(report_chief) or int(run_model)!=int(call_model)
        or int(run_chars)<=0 or int(call_chars)<=0
        or hashlib.sha256(str(body).encode()).hexdigest()!=digest
        or hashlib.sha256(str(report).encode()).hexdigest()!=report_sha):
        raise ValueError('고객지원 결과물·총괄 승인·실제 호출 증빙이 일치하지 않습니다.')
    return digest


def _chief_call_audited(con, artifact_id: int) -> bool:
    """Audit linkage only; not an independent GGUF-binary attestation."""
    row=con.execute("""SELECT rep.chief_model_call_id,rep.chief_employee_id,
        h.employee_id,h.status,h.output_chars,h.id,r.model_call_id,
        rep.owner_decision,a.review_status
        FROM company_chief_task_reports rep
        JOIN company_task_artifacts a ON a.id=rep.artifact_id
        JOIN company_task_runs r ON r.id=a.run_id
        LEFT JOIN ai_model_call_history h ON h.id=rep.chief_model_call_id
        WHERE rep.artifact_id=?""",(artifact_id,)).fetchone()
    # Reusing a successful CEO call for two unrelated customer replies is
    # not proof that the CEO actually reviewed both of them.
    if not row or row[0] is None or con.execute(
            'SELECT COUNT(*) FROM company_chief_task_reports WHERE chief_model_call_id=?',
            (row[0],)).fetchone()[0]!=1:
        return False
    return bool(row[0]==row[5]
                and row[1]==row[2] and row[3]=='success' and row[4]>0
                and row[6] is not None and row[5]>row[6]
                and row[7]=='accepted' and row[8]=='approved')


def attach_approved_reply(store,case_id:int,artifact_id:int)->dict:
    store.require_permission('company:manage')
    if any(type(x) is not int or x<=0 for x in (case_id,artifact_id)):
        raise ValueError('고객 문의·결과물 번호 오류')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE');initialize(con)
        if stopped(con):raise PermissionError('비상정지 중에는 고객 답변 검수가 불가합니다.')
        case=con.execute('SELECT task_id,state,case_ref,question FROM aiwack_customer_cases WHERE id=?',(case_id,)).fetchone()
        if not case or case[1]!='open':raise ValueError('답변 검수 대기 상태가 아닙니다.')
        source=con.execute('SELECT title,description FROM company_tasks WHERE id=?',(case[0],)).fetchone()
        if not source or tuple(source)!=(('고객지원 문의 '+case[2])[:120],case[3]):
            raise ValueError('변경된 고객 문의 업무의 결과를 승인할 수 없습니다.')
        digest=_reply_proof(con,int(case[0]),artifact_id)
        result=con.execute('''UPDATE aiwack_customer_cases SET state='response_ready',
                 artifact_id=?,reply_sha256=?,decided_at=CURRENT_TIMESTAMP
                 WHERE id=? AND state='open' ''',(artifact_id,digest,case_id))
        if result.rowcount!=1:raise ValueError('다른 세션의 답변 검수와 충돌했습니다.')
        _event(con,case_id,'response_ready','open','response_ready',artifact_id,digest)
    return read(store,case_id)


def close(store,case_id:int)->dict:
    """Owner closes an INTERNAL support record; never claims message was sent."""
    store.require_permission('company:manage')
    if type(case_id) is not int or case_id<=0:raise ValueError('고객 문의 번호 오류')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE');initialize(con)
        if stopped(con):raise PermissionError('비상정지 중 고객 업무 완료 처리 불가')
        case=con.execute('SELECT task_id,state,artifact_id,reply_sha256 FROM aiwack_customer_cases WHERE id=?',
                         (case_id,)).fetchone()
        if not case or case[1]!='response_ready':
            raise ValueError('관리자 승인된 고객 답변이 있어야 종료할 수 있습니다.')
        proof=_reply_proof(con,int(case[0]),int(case[2]))
        if proof!=case[3]:raise ValueError('고객 답변 원본이 변경됐습니다.')
        con.execute("UPDATE aiwack_customer_cases SET state='closed' WHERE id=?",(case_id,))
        _event(con,case_id,'closed','response_ready','closed',int(case[2]),case[3])
    return read(store,case_id)


def read(store,case_id:int)->dict:
    store.require_permission('company:manage')
    if type(case_id) is not int or case_id<=0:raise ValueError('고객 문의 번호 오류')
    with store._connect() as con:
        initialize(con)
        row=con.execute('''SELECT case_ref,customer_alias,question,task_id,catalog_item_id,
                            state,artifact_id,reply_sha256 FROM aiwack_customer_cases
                            WHERE id=?''',(case_id,)).fetchone()
        if not row:raise ValueError('고객 문의가 없습니다.')
        ref,alias,question,task,catalog,state,artifact,digest=row
        original=con.execute('SELECT title,description FROM company_tasks WHERE id=?',(task,)).fetchone()
        if not original or original[0]!=('고객지원 문의 '+ref)[:120] or original[1]!=question:
            raise ValueError('고객 문의 원본과 연결 업무가 변경되었습니다.')
        routed=con.execute('''SELECT d.name FROM company_task_routing r
                  JOIN company_departments d ON d.id=r.department_id
                  WHERE r.task_id=?''',(task,)).fetchone()
        if not routed or routed[0]!='고객지원부':
            raise ValueError('고객지원부 연결이 손상되었습니다.')
        events=con.execute('''SELECT action,old_state,new_state,artifact_id,reply_sha256
                  FROM aiwack_customer_case_events WHERE case_id=? ORDER BY id''',
                  (case_id,)).fetchall()
        expected=[('created','','open',None,'')]
        if state in ('response_ready','closed'):
            expected.append(('response_ready','open','response_ready',artifact,digest))
            if _reply_proof(con,int(task),int(artifact))!=digest:
                raise ValueError('고객지원 직원 결과물 해시 손상')
        if state=='closed':expected.append(('closed','response_ready','closed',artifact,digest))
        if [tuple(x) for x in events]!=expected:
            raise ValueError('고객 문의 감사 이력과 상태가 일치하지 않습니다.')
        chief_call_audited=bool(artifact and _chief_call_audited(con,int(artifact)))
    return {'id':case_id,'case_ref':ref,'customer_alias':alias,'question':question,
            'task_id':int(task),'catalog_item_id':catalog,'state':state,
            'artifact_id':artifact,'reply_sha256':digest,
            'actual_customer_reply_sent':False,'provider_order_verified':False,
            'chief_model_call_audited':chief_call_audited,
            'actual_gguf_binary_verified':False,'payment_processed':False}


def _init_reply_exports(con):
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_customer_reply_exports(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_customer_cases(id),
        artifact_id INTEGER NOT NULL REFERENCES company_task_artifacts(id),
        reply_sha256 TEXT NOT NULL CHECK(length(reply_sha256)=64),
        filename TEXT NOT NULL UNIQUE,
        file_sha256 TEXT NOT NULL CHECK(length(file_sha256)=64),
        file_bytes INTEGER NOT NULL CHECK(file_bytes BETWEEN 1 AND 65536),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    for operation in ('UPDATE','DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS aiwack_customer_reply_export_no_{operation.lower()}
          BEFORE {operation} ON aiwack_customer_reply_exports BEGIN
          SELECT RAISE(ABORT,'고객지원 승인 답변 파일 기록 수정·삭제 금지'); END''')


def _reply_file_bytes(con,task_id,artifact_id,reply_digest,case_id):
    proof=_reply_proof(con,task_id,artifact_id)
    if proof!=reply_digest:
        raise ValueError('고객 답변 승인 원본이 변경됐습니다.')
    row=con.execute('''SELECT a.body,r.body FROM company_task_artifacts a
       JOIN company_chief_task_reports r ON r.artifact_id=a.id
       WHERE a.id=? AND r.owner_decision='accepted' AND a.review_status='approved' ''',
       (artifact_id,)).fetchone()
    if not row:
        raise ValueError('고객 답변 승인 보고서가 없습니다.')
    data=(f'# 관리자 승인 고객지원 답변 #{case_id}\n\n'
          f'직원 결과물 #{artifact_id}\n\n{row[0]}\n\n'
          f'---\n총괄 AI 검토 보고\n\n{row[1]}\n\n'
          '외부 고객에게 전송하지 않은 로컬 승인 문서입니다.\n').encode('utf-8')
    if not 1<=len(data)<=65536:
        raise ValueError('고객 답변 문서가 64KiB 크기를 초과했습니다.')
    return data


def export_approved_reply(store,case_id:int)->dict:
    """Write an approved reply to a real local file; NEVER send externally."""
    from pathlib import Path
    from uuid import uuid4
    import os
    store.require_permission('company:manage')
    if type(case_id) is not int or case_id<=0:
        raise ValueError('고객 문의 번호 오류')
    case=read(store,case_id)
    if case['state'] not in ('response_ready','closed'):
        raise ValueError('승인된 고객 답변만 파일로 보존할 수 있습니다.')
    folder=Path(store.path).resolve().parent/'aiwack_customer_reply_documents'
    if folder.is_symlink():
        raise ValueError('고객 답변 파일 폴더 링크 금지')
    filename='reply_'+uuid4().hex+'.md'
    path=folder/filename
    temp_path=folder/('.'+filename+'.tmp')
    written=False
    committed=False
    try:
        with store._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            initialize(con)
            _init_reply_exports(con)
            if stopped(con):
                raise PermissionError('비상정지 중 고객 답변 파일 생성 금지')
            row=con.execute('''SELECT state,task_id,artifact_id,reply_sha256
                FROM aiwack_customer_cases WHERE id=?''',(case_id,)).fetchone()
            if not row or row[0] not in ('response_ready','closed'):
                raise ValueError('고객 답변의 승인 상태가 변경됐습니다.')
            source=con.execute('''SELECT t.title,t.description,c.case_ref,c.question
                FROM company_tasks t JOIN aiwack_customer_cases c ON c.task_id=t.id
                WHERE c.id=?''',(case_id,)).fetchone()
            if not source or source[0]!=('고객지원 문의 '+source[2])[:120] or source[1]!=source[3]:
                raise ValueError('고객지원 문의 원본과 업무가 변경됐습니다.')
            if con.execute('SELECT 1 FROM aiwack_customer_reply_exports WHERE case_id=?',
                           (case_id,)).fetchone():
                raise ValueError('이미 내보낸 고객 답변 파일이 있습니다.')
            data=_reply_file_bytes(con,int(row[1]),int(row[2]),str(row[3]),case_id)
            folder.mkdir(parents=True,exist_ok=True)
            if folder.is_symlink():
                raise ValueError('고객 답변 파일 폴더 링크 금지')
            # Publish a complete flushed file, never a half-written reply.
            with temp_path.open('xb') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            if folder.is_symlink() or path.exists() or path.is_symlink():
                raise ValueError('고객 답변 저장 경로가 변경됐습니다.')
            os.replace(temp_path,path)
            written=True
            export_id=int(con.execute('''INSERT INTO aiwack_customer_reply_exports
                (case_id,artifact_id,reply_sha256,filename,file_sha256,file_bytes)
                VALUES(?,?,?,?,?,?)''',
                (case_id,int(row[2]),str(row[3]),filename,
                 hashlib.sha256(data).hexdigest(),len(data))).lastrowid)
        committed=True
        return read_export(store,export_id)
    except BaseException:
        # Roll back the file on SQLite errors and clear unfinished temp files.
        temp_path.unlink(missing_ok=True)
        if written and not committed:
            path.unlink(missing_ok=True)
        raise


def read_export(store,export_id:int)->dict:
    from pathlib import Path
    store.require_permission('company:manage')
    if type(export_id) is not int or export_id<=0:
        raise ValueError('고객 답변 파일 번호 오류')
    with store._connect() as con:
        initialize(con)
        _init_reply_exports(con)
        row=con.execute('''SELECT case_id,artifact_id,reply_sha256,filename,file_sha256,file_bytes
          FROM aiwack_customer_reply_exports WHERE id=?''',(export_id,)).fetchone()
        if not row:
            raise ValueError('고객 답변 파일 기록 없음')
        case_id,artifact_id,reply_digest,filename,file_digest,size=row
        case=con.execute('SELECT task_id,state,artifact_id,reply_sha256 FROM aiwack_customer_cases WHERE id=?',
                         (case_id,)).fetchone()
        if not case or case[1] not in ('response_ready','closed') or case[2]!=artifact_id or case[3]!=reply_digest:
            raise ValueError('고객 답변 파일과 승인 상태가 일치하지 않습니다.')
        data=_reply_file_bytes(con,int(case[0]),int(artifact_id),str(reply_digest),int(case_id))
    # The export row alone cannot prove the original customer inquiry survived.
    read(store,int(case_id))
    if (type(filename) is not str or not filename.startswith('reply_') or
        len(filename)!=41 or not filename.endswith('.md') or
        any(c not in '0123456789abcdef' for c in filename[6:-3])):
        raise ValueError('고객 답변 파일 이름 무결성 오류')
    folder=Path(store.path).resolve().parent/'aiwack_customer_reply_documents'
    path=folder/filename
    if folder.is_symlink() or path.is_symlink() or not path.is_file():
        raise ValueError('고객 답변 파일이 없거나 심볼릭 링크입니다.')
    saved=path.read_bytes()
    if len(saved)!=size or saved!=data or hashlib.sha256(saved).hexdigest()!=file_digest:
        raise ValueError('고객 답변 파일 내용 또는 해시 무결성 손상')
    return {'id':export_id,'case_id':case_id,'artifact_id':artifact_id,
            'path':str(path),'file_sha256':file_digest,'file_bytes':size,
            'actual_customer_reply_sent':False,'external_message_delivered':False}