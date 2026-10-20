"""Durable, owner-confirmed local company work campaign (up to 31 tasks).

Existing models really run; no mock output, payment, external tool, autonomous
approval, task completion or invisible retry. A campaign is explicitly started
in the company GUI and runs only while that application/session is open.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
from uuid import uuid4

from desktop import company_operations as ops


def initialize(store) -> None:
    store.require_permission('company:manage')
    with store._connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS aiwack_work_campaigns(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state TEXT NOT NULL CHECK(state IN ('draft','running','paused','review_pending')),
            label TEXT NOT NULL,
            last_error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("""CREATE TABLE IF NOT EXISTS aiwack_work_campaign_items(
            campaign_id INTEGER NOT NULL REFERENCES aiwack_work_campaigns(id),
            task_id INTEGER NOT NULL UNIQUE REFERENCES company_tasks(id),
            employee_id INTEGER NOT NULL,
            ordinal INTEGER NOT NULL,
            state TEXT NOT NULL CHECK(state IN
                ('pending','running','review_pending','needs_review')),
            artifact_id INTEGER,
            note TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(campaign_id,task_id),
            UNIQUE(campaign_id,ordinal))""")
        con.execute("""CREATE INDEX IF NOT EXISTS aiwack_campaign_by_state
                       ON aiwack_work_campaigns(state,id)""")
        con.execute("""CREATE TABLE IF NOT EXISTS aiwack_work_campaign_leases(
            campaign_id INTEGER PRIMARY KEY REFERENCES aiwack_work_campaigns(id),
            owner_token TEXT NOT NULL CHECK(length(owner_token)=32),
            heartbeat_epoch INTEGER NOT NULL)""")


def candidate_tasks(store, *, limit: int = 31) -> list[dict]:
    """Preview every task that has an owner's prior approved chief order."""
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 31:
        raise ValueError('운영 대상 업무는 1~31건이어야 합니다.')
    initialize(store)
    with store._connect() as con:
        reserved = {int(row[0]) for row in
                    con.execute('SELECT task_id FROM aiwack_work_campaign_items')}
    result = []
    for task in sorted(store.list_tasks(), key=lambda t: int(t['id'])):
        tid = int(task['id'])
        if tid in reserved or task['status'] != 'todo':
            continue
        if store.read_chief_task_order(tid) is None:
            continue
        if store.list_task_runs(tid) or store.list_task_artifacts(tid):
            continue
        with store._connect() as con:
            if store._pending_prerequisites(con,tid):
                continue
        route = store.read_task_routing(tid)
        eid = route['employee_id']
        if not eid or store.read_employee_model(int(eid)) is None:
            continue
        result.append({'task_id':tid,'employee_id':int(eid),'title':str(task['title'])})
        if len(result) == limit:
            break
    return result


def create_campaign(store, *, expected_task_ids: tuple[int,...], label: str = '승인된 사내 AI 공동업무') -> int:
    """Write the immutable human-confirmed manifest; NEVER dispatch here."""
    store.require_permission('company:manage')
    if (type(expected_task_ids) is not tuple or not 1 <= len(expected_task_ids) <= 31
            or any(type(t) is not int or t <= 0 for t in expected_task_ids)
            or len(set(expected_task_ids)) != len(expected_task_ids)):
        raise ValueError('승인한 업무 번호 1~31개가 정확해야 합니다.')
    if not isinstance(label,str) or not 1 <= len(label.strip()) <= 100:
        raise ValueError('운영 작업 이름을 확인하세요.')
    candidates=candidate_tasks(store,limit=len(expected_task_ids))
    if tuple(t['task_id'] for t in candidates) != expected_task_ids:
        raise ValueError('관리자가 확인한 업무와 현재 승인 업무가 일치하지 않습니다.')
    # Lock SQLite before writing the immutable manifest, so another
    # owner's GUI cannot create the same campaign concurrently.
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        for item in candidates:
            tid=item['task_id']
            row=con.execute('SELECT status FROM company_tasks WHERE id=?',(tid,)).fetchone()
            if not row or row[0]!='todo' or con.execute(
                'SELECT 1 FROM aiwack_work_campaign_items WHERE task_id=?',(tid,)).fetchone():
                raise ValueError('동일 업무가 이미 다른 운영 작업에 등록됐습니다.')
        campaign_id=int(con.execute(
            "INSERT INTO aiwack_work_campaigns(state,label) VALUES('draft',?)",
            (label.strip(),)).lastrowid)
        for position,item in enumerate(candidates):
            con.execute("""INSERT INTO aiwack_work_campaign_items(
                campaign_id,task_id,employee_id,ordinal,state)
                VALUES(?,?,?,?,'pending')""",
                (campaign_id,item['task_id'],item['employee_id'],position))
    return campaign_id


def campaign_status(store, campaign_id: int) -> dict:
    store.require_permission('company:manage')
    initialize(store)
    if type(campaign_id) is not int or campaign_id <= 0:
        raise ValueError('운영 작업 번호가 올바르지 않습니다.')
    with store._connect() as con:
        row=con.execute(
            'SELECT id,label,state,last_error,created_at FROM aiwack_work_campaigns WHERE id=?',
            (campaign_id,)).fetchone()
        if row is None:
            raise ValueError('운영 작업을 찾을 수 없습니다.')
        items=con.execute("""SELECT task_id,employee_id,ordinal,state,artifact_id,note
             FROM aiwack_work_campaign_items WHERE campaign_id=? ORDER BY ordinal""",
             (campaign_id,)).fetchall()
    entries=[dict(zip(('task_id','employee_id','ordinal','state','artifact_id','note'),x))
             for x in items]
    return {'id':int(row[0]),'label':row[1],'state':row[2],
            'last_error':row[3],'created_at':row[4],'items':entries,
            'total':len(entries),
            'pending':sum(x['state']=='pending' for x in entries),
            'review_pending':sum(x['state']=='review_pending' for x in entries),
            'needs_review':sum(x['state']=='needs_review' for x in entries),
            'running':sum(x['state']=='running' for x in entries),
            'auto_approved':False}


def list_campaigns(store, limit: int = 20) -> list[dict]:
    store.require_permission('company:manage')
    initialize(store)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('조회 건수는 1~100이어야 합니다.')
    with store._connect() as con:
        ids=[int(r[0]) for r in con.execute(
            'SELECT id FROM aiwack_work_campaigns ORDER BY id DESC LIMIT ?', (limit,))]
    return [campaign_status(store,cid) for cid in ids]


def inspect_interrupted_campaign(store, campaign_id: int) -> dict:
    """Owner-visible audit, not an automatic retry after an EXE crash."""
    store.require_permission('company:manage')
    initialize(store)
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        row=con.execute('SELECT state FROM aiwack_work_campaigns WHERE id=?',
                        (campaign_id,)).fetchone()
        if not row:
            raise ValueError('운영 작업이 존재하지 않습니다.')
        if row[0]=='running':
            lease=con.execute('SELECT heartbeat_epoch FROM aiwack_work_campaign_leases WHERE campaign_id=?',
                              (campaign_id,)).fetchone()
            if lease is not None and int(time.time())-int(lease[0]) < 90:
                raise ValueError('다른 AIWACK 창에서 실행 중인 운영 작업입니다. 살아 있는 실행을 중단 처리하지 않습니다.')
            con.execute('DELETE FROM aiwack_work_campaign_leases WHERE campaign_id=?',(campaign_id,))
            con.execute("""UPDATE aiwack_work_campaign_items
                SET state='needs_review',note='종료된 실행 여부를 관리자 확인 필요'
                WHERE campaign_id=? AND state='running'""",(campaign_id,))
            con.execute("""UPDATE aiwack_work_campaigns
                SET state='paused',last_error='중단된 업무는 자동 재실행하지 않습니다.',
                    updated_at=CURRENT_TIMESTAMP WHERE id=?""",(campaign_id,))
    return campaign_status(store,campaign_id)


def reconcile_manually_recovered_chief_reviews(store, campaign_id: int) -> dict:
    """Reconcile ONLY already persisted chief reports; never rerun a model.

    An interrupted item without a chief report stays in needs_review. The
    existing owner-controlled recovery screen can separately review it.
    """
    state=campaign_status(store,campaign_id)
    if state['state']!='paused':
        raise ValueError('중단되어 관리자가 확인한 운영 작업만 다시 대조할 수 있습니다.')
    matched=[]
    for item in state['items']:
        if item['state']!='needs_review':
            continue
        artifacts=store.list_task_artifacts(item['task_id'])
        if len(artifacts)!=1:
            continue
        artifact_id=int(artifacts[0]['id'])
        report=store.find_chief_task_report(artifact_id)
        if not report or int(report['artifact_id'])!=artifact_id:
            continue
        if store.read_task(item['task_id'])['status']!='in_progress':
            continue
        with store._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            changed=con.execute("""UPDATE aiwack_work_campaign_items
                SET state='review_pending',artifact_id=?,
                    note='관리자가 기존 총괄 검토와 연결함; 재실행 없음'
                WHERE campaign_id=? AND task_id=? AND state='needs_review'""",
                (artifact_id,campaign_id,item['task_id'])).rowcount
            if changed==1:matched.append(item['task_id'])
    result=campaign_status(store,campaign_id)
    result['reconciled_existing_chief_reports']=matched
    result['models_reexecuted']=False
    return result


def _set_item(store, cid, tid, state, *, artifact_id=None, note=''):
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        changed=con.execute("""UPDATE aiwack_work_campaign_items
            SET state=?,artifact_id=COALESCE(?,artifact_id),note=?
            WHERE campaign_id=? AND task_id=? AND state='running'""",
            (state,artifact_id,note[:350],cid,tid)).rowcount
        if changed!=1:
            raise RuntimeError('운영 작업 감사 상태가 변경됐습니다. 실행을 중단합니다.')


def _pause(store, cid, message):
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        con.execute("""UPDATE aiwack_work_campaign_items SET
            state='needs_review',note='중단 시 진행 중인 실행 기록 수동 확인 필요'
            WHERE campaign_id=? AND state='running'""",(cid,))
        con.execute("""UPDATE aiwack_work_campaigns SET
            state='paused',last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (str(message)[:350],cid))


def execute_campaign(store, campaign_id: int, *,
                     cancel: threading.Event | None = None,
                     max_parallel: int = 2) -> dict:
    """Dispatch a pre-approved manifest in bounded waves, no silent retries."""
    ops.assert_running_allowed(store)
    if type(max_parallel) is not int or max_parallel not in (1,2):
        raise ValueError('직원 AI 동시 실행은 1~2명입니다.')
    if cancel is not None and cancel.is_set():
        raise InterruptedError('소유자가 시작 전에 취소했습니다.')
    current=campaign_status(store,campaign_id)
    if current['state'] not in ('draft','paused') or current['needs_review'] or current['running']:
        raise ValueError('중단된 실행은 먼저 관리자가 기록을 확인해야 합니다.')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        row=con.execute('SELECT state FROM aiwack_work_campaigns WHERE id=?',
                        (campaign_id,)).fetchone()
        if row is None or row[0] not in ('draft','paused'):
            raise ValueError('다른 프로그램에서 이미 실행 중인 운영 작업입니다.')
        if con.execute("""SELECT 1 FROM aiwack_work_campaign_items
            WHERE campaign_id=? AND state IN ('running','needs_review')""",(campaign_id,)).fetchone():
            raise ValueError('재실행 전에 중단 업무 감사를 확인하세요.')
        con.execute("""UPDATE aiwack_work_campaigns SET state='running',
            last_error='',updated_at=CURRENT_TIMESTAMP WHERE id=?""",(campaign_id,))
        lease_token=uuid4().hex
        con.execute("""INSERT INTO aiwack_work_campaign_leases(campaign_id,owner_token,heartbeat_epoch)
            VALUES(?,?,?) ON CONFLICT(campaign_id) DO UPDATE SET
            owner_token=excluded.owner_token,heartbeat_epoch=excluded.heartbeat_epoch""",
            (campaign_id,lease_token,int(time.time())))
    token=cancel if cancel is not None else threading.Event()
    keepalive_stop=threading.Event()
    keepalive_errors=[]
    def heartbeat():
        while not keepalive_stop.wait(5):
            try:
                with store._connect() as con:
                    con.execute('BEGIN IMMEDIATE')
                    affected=con.execute("""UPDATE aiwack_work_campaign_leases SET heartbeat_epoch=?
                        WHERE campaign_id=? AND owner_token=? AND
                        EXISTS(SELECT 1 FROM aiwack_work_campaigns
                               WHERE id=? AND state='running')""",
                        (int(time.time()),campaign_id,lease_token,campaign_id)).rowcount
                    if affected!=1:
                        raise RuntimeError('다른 세션이 운영 실행 소유권을 변경했습니다.')
            except Exception as exc:
                keepalive_errors.append(exc)
                token.set()
                break
    keeper=threading.Thread(target=heartbeat,name='AIWACK-campaign-heartbeat',daemon=True)
    keeper.start()
    try:
        while True:
            if keepalive_errors:
                raise RuntimeError('운영 작업 실행 소유권이 유지되지 않았습니다.') from keepalive_errors[0]
            if token.is_set():
                raise InterruptedError('소유자가 사내 AI 운영을 중단했습니다.')
            ops.assert_running_allowed(store)
            status=campaign_status(store,campaign_id)
            pending=[x for x in status['items'] if x['state']=='pending']
            if not pending:
                with store._connect() as con:
                    con.execute('BEGIN IMMEDIATE')
                    con.execute("""UPDATE aiwack_work_campaigns SET
                        state='review_pending',updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                        (campaign_id,))
                return campaign_status(store,campaign_id)
            chosen=[]
            distinct=set()
            for item in pending:
                if item['employee_id'] in distinct:
                    continue
                chosen.append(item)
                distinct.add(item['employee_id'])
                if len(chosen)>=max_parallel:
                    break
            # Manifest is immutable, but orders, assignments and prerequisites
            # may have changed in another owner's window since confirmation.
            for item in chosen:
                tid=item['task_id']
                task=store.read_task(tid)
                route=store.read_task_routing(tid)
                with store._connect() as con:
                    blocked=bool(store._pending_prerequisites(con,tid))
                if (task['status']!='todo' or route['employee_id']!=item['employee_id']
                        or store.read_chief_task_order(tid) is None or blocked
                        or store.read_employee_model(item['employee_id']) is None
                        or store.list_task_runs(tid) or store.list_task_artifacts(tid)):
                    raise ValueError(f'승인된 업무 #{tid}의 상태가 변경됐습니다. 재확인하세요.')
            with store._connect() as con:
                con.execute('BEGIN IMMEDIATE')
                for item in chosen:
                    if con.execute('SELECT status FROM company_tasks WHERE id=?',
                        (item['task_id'],)).fetchone()[0]!='todo':
                        raise ValueError('다른 운영 창이 업무를 변경했습니다.')
                    changed=con.execute("""UPDATE aiwack_work_campaign_items
                        SET state='running' WHERE campaign_id=? AND task_id=? AND state='pending'""",
                        (campaign_id,item['task_id'])).rowcount
                    if changed!=1:
                        raise ValueError('다른 프로그램이 운영 작업을 선점했습니다.')
            results={}
            errors={}
            with ThreadPoolExecutor(max_workers=len(chosen),thread_name_prefix='AIWACK-team') as pool:
                futures={pool.submit(ops.execute_task,store,item['task_id'],cancel=token):
                         item['task_id'] for item in chosen}
                for future in as_completed(futures):
                    tid=futures[future]
                    try:
                        results[tid]=future.result()
                    except Exception as exc:
                        errors[tid]=exc
                        token.set()
            if errors:
                raise next(iter(errors.values()))
            if token.is_set():
                raise InterruptedError('직원 업무 실행 후 중단되어 총괄 검토를 하지 않습니다.')
            for item in chosen:
                tid=item['task_id']
                ops.assert_running_allowed(store)
                if token.is_set():
                    raise InterruptedError('총괄 검토 시작 전 중단되었습니다.')
                report=ops.collect_chief_review(store,int(results[tid]['artifact_id']),cancel=token)
                if token.is_set():
                    raise InterruptedError('총괄 검토 후 관리자가 중단했습니다.')
                if not report or int(report['artifact_id'])!=int(results[tid]['artifact_id']):
                    raise RuntimeError('총괄 AI 검토 결과가 업무와 일치하지 않습니다.')
                _set_item(store,campaign_id,tid,'review_pending',
                          artifact_id=int(results[tid]['artifact_id']),
                          note='결과물은 소유자 승인 대기')
    except Exception as exc:
        _pause(store,campaign_id,exc)
        raise
    finally:
        keepalive_stop.set()
        keeper.join(timeout=12)
        with store._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            con.execute('DELETE FROM aiwack_work_campaign_leases WHERE campaign_id=? AND owner_token=?',
                        (campaign_id,lease_token))
