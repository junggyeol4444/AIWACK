"""관리자 승인 HMAC 거래/은행 CSV 대사의 사업별 결산 및 감사 원장.

독립 은행·PG 검증 또는 실제 자금 정산 기능이 아니다. 기존 원본은 변경하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from desktop import company_bank_reconciliation as bank
from desktop import company_payment_reconciliation as provider
from desktop.stage87_90_management import stopped

KINDS = ('settlement', 'refund', 'expense')


def initialize(con: sqlite3.Connection) -> None:
    bank.initialize(con)
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_business_financial_closes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id INTEGER NOT NULL REFERENCES managed_businesses(id) ON DELETE RESTRICT,
        cutoff_event_id INTEGER NOT NULL CHECK(cutoff_event_id>0),
        accepted_count INTEGER NOT NULL CHECK(accepted_count>0),
        accepted_net_minor INTEGER NOT NULL,
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        statement_sha256 TEXT NOT NULL CHECK(length(statement_sha256)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(business_id,cutoff_event_id))''')
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_business_financial_close_lines (
        close_id INTEGER NOT NULL REFERENCES aiwack_business_financial_closes(id) ON DELETE RESTRICT,
        payment_event_id INTEGER NOT NULL REFERENCES aiwack_provider_payment_events(id) ON DELETE RESTRICT,
        bank_match_id INTEGER NOT NULL REFERENCES aiwack_bank_reconciliation_matches(id) ON DELETE RESTRICT,
        event_sha256 TEXT NOT NULL CHECK(length(event_sha256)=64),
        amount_minor INTEGER NOT NULL CHECK(amount_minor>0),
        PRIMARY KEY(close_id,payment_event_id),
        UNIQUE(close_id,bank_match_id))''')
    # Additive v2 period links: historical v1 statements retain their original
    # hashes and original full-to-cutoff semantics; no schema rewrite required.
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_business_financial_close_periods (
        close_id INTEGER PRIMARY KEY REFERENCES aiwack_business_financial_closes(id) ON DELETE RESTRICT,
        period_start_event_id INTEGER NOT NULL CHECK(period_start_event_id>0),
        previous_close_id INTEGER REFERENCES aiwack_business_financial_closes(id) ON DELETE RESTRICT,
        previous_statement_sha256 TEXT NOT NULL DEFAULT '',
        statement_version INTEGER NOT NULL CHECK(statement_version=2),
        CHECK ((previous_close_id IS NULL AND previous_statement_sha256='') OR
               (previous_close_id IS NOT NULL AND length(previous_statement_sha256)=64))
    )''')
    for table in ('aiwack_business_financial_closes','aiwack_business_financial_close_lines',
                  'aiwack_business_financial_close_periods'):
        for verb in ('UPDATE','DELETE'):
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_immutable_{verb.lower()}
                BEFORE {verb} ON {table} BEGIN
                SELECT RAISE(ABORT,'확정 결산 및 거래 연결 원문 변경 금지'); END''')


def _rows(con, business_id: int, cutoff: int | None = None, start: int = 1) -> tuple[list, list]:
    sql = '''SELECT p.id,p.provider,p.event_type,p.amount_minor,p.event_sha256,
                    p.owner_decision,m.id,m.event_sha256,m.amount_minor
             FROM aiwack_provider_payment_events p
             LEFT JOIN aiwack_bank_reconciliation_matches m ON m.payment_event_id=p.id
             WHERE p.business_id=?'''
    sql += ' AND p.id>=?'
    params = [business_id, start]
    if cutoff is not None:
        sql += ' AND p.id<=?'
        params.append(cutoff)
    sql += ' ORDER BY p.id'
    entries=con.execute(sql,params).fetchall()
    ready=[];blockers=[]
    for eid,source,kind,amount,digest,state,match_id,matched_digest,matched_amount in entries:
        if state!='accepted':
            blockers.append({'event_id':eid,'reason':'검수 대기 또는 반려 거래'})
            continue
        if (match_id is None or digest!=matched_digest or amount!=matched_amount):
            blockers.append({'event_id':eid,'reason':'관리자 CSV 대사 누락 또는 원본 불일치'})
            continue
        if kind not in KINDS or not source or amount<=0:
            blockers.append({'event_id':eid,'reason':'승인 거래 원본 형식 오류'})
            continue
        ready.append((int(eid),int(match_id),str(digest),kind,int(amount)))
    return ready,blockers


def _latest_close(con, business_id: int):
    return con.execute('''SELECT id,cutoff_event_id,statement_sha256
        FROM aiwack_business_financial_closes WHERE business_id=?
        ORDER BY cutoff_event_id DESC,id DESC LIMIT 1''',(business_id,)).fetchone()


def _statement(business: int, cutoff: int, ready: list, note: str, *,
               period_start: int | None = None, previous: tuple | None = None) -> dict:
    totals={k:0 for k in KINDS}
    for _eid,_mid,_sha,kind,amount in ready:
        totals[kind]+=amount
    result={'business_id':business,'cutoff_event_id':cutoff,
            'owner_note':note,'currency':'KRW','accepted_count':len(ready),
            'amounts_minor':totals,
            'net_minor':totals['settlement']-totals['refund']-totals['expense'],
            'lines':[{'payment_event_id':eid,'bank_match_id':mid,
                      'event_sha256':sha,'event_type':kind,'amount_minor':amount}
                     for eid,mid,sha,kind,amount in ready],
            'bank_csv_locally_reconciled':True,
            'independently_verified_bank_or_provider':False,
            'actual_payment_or_refund_executed':False}
    if period_start is not None:
        result.update(statement_version=2,period_start_event_id=period_start,
                      prior_close_id=previous[0] if previous else None,
                      prior_close_sha256=previous[2] if previous else '')
    return result


def _digest(statement: dict) -> str:
    raw=json.dumps(statement,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def preview(store,business_id:int) -> dict:
    """미확정 거래/불일치 목록 조회. 거래나 결산 데이터를 변경하지 않음."""
    store.require_permission('company:manage')
    if type(business_id) is not int or business_id<=0:
        raise ValueError('사업 번호는 양의 정수여야 합니다.')
    with store._connect() as con:
        initialize(con)
        if not con.execute('SELECT 1 FROM managed_businesses WHERE id=?',(business_id,)).fetchone():
            raise ValueError('사업 기록 없음')
        prev=_latest_close(con,business_id)
        start=int(prev[1])+1 if prev else 1
        ready,blockers=_rows(con,business_id,start=start)
        cutoff=con.execute('''SELECT MAX(id) FROM aiwack_provider_payment_events
            WHERE business_id=?''',(business_id,)).fetchone()[0] or 0
    note='관리자 결산 사전 점검'
    snapshot=_statement(business_id,cutoff,ready,note,period_start=start,previous=prev)
    return {'business_id':business_id,'cutoff_event_id':cutoff,'period_start_event_id':start,
            'previous_close_id':prev[0] if prev else None,
            'accepted_and_matched':len(ready),'blocked':blockers,
            'amounts_minor':snapshot['amounts_minor'],'net_minor':snapshot['net_minor'],
            'eligible_for_local_close':bool(ready) and not blockers,
            'independently_verified_bank_or_provider':False}


def create(store,business_id:int,note:str)->dict:
    """관리자가 명시적으로 확정. 한 시점의 대사 원문을 고정하고 자동 결제·송금은 금지."""
    store.require_permission('company:manage')
    if type(business_id) is not int or business_id<=0:
        raise ValueError('사업 번호 오류')
    if not isinstance(note,str) or not 5<=len(note.strip())<=200:
        raise ValueError('관리자 결산 사유 5~200자 필요')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        if stopped(con):raise PermissionError('비상정지 중 결산 확정 불가')
        if not con.execute('SELECT 1 FROM managed_businesses WHERE id=?',(business_id,)).fetchone():
            raise ValueError('사업 기록 없음')
        cutoff=con.execute('''SELECT MAX(id) FROM aiwack_provider_payment_events
                 WHERE business_id=?''',(business_id,)).fetchone()[0] or 0
        prev=_latest_close(con,business_id)
        if prev:
            _verify_close(con,int(prev[0]))
        start=int(prev[1])+1 if prev else 1
        ready,blockers=_rows(con,business_id,cutoff,start=start)
        if blockers:raise ValueError('검수 미완료·미대사 거래 또는 원본 불일치가 있어 확정할 수 없습니다.')
        if not ready:
            if prev and cutoff==prev[1]:
                raise ValueError('동일 시점의 확정 결산이 이미 있습니다.')
            raise ValueError('관리자 승인·은행 CSV 대사가 모두 완료된 신규 거래가 없습니다.')
        if con.execute('''SELECT 1 FROM aiwack_business_financial_closes
                  WHERE business_id=? AND cutoff_event_id=?''',(business_id,cutoff)).fetchone():
            raise ValueError('동일 시점의 확정 결산이 이미 있습니다.')
        statement=_statement(business_id,cutoff,ready,note.strip(),period_start=start,previous=prev)
        close_id=con.execute('''INSERT INTO aiwack_business_financial_closes
            (business_id,cutoff_event_id,accepted_count,accepted_net_minor,owner_note,statement_sha256)
            VALUES(?,?,?,?,?,?)''',
            (business_id,cutoff,len(ready),statement['net_minor'],note.strip(),_digest(statement))).lastrowid
        con.execute('''INSERT INTO aiwack_business_financial_close_periods
            (close_id,period_start_event_id,previous_close_id,previous_statement_sha256,statement_version)
            VALUES(?,?,?,?,2)''',
            (close_id,start,prev[0] if prev else None,prev[2] if prev else ''))
        for eid,mid,sha,kind,amount in ready:
            con.execute('''INSERT INTO aiwack_business_financial_close_lines
                (close_id,payment_event_id,bank_match_id,event_sha256,amount_minor)
                VALUES(?,?,?,?,?)''',(close_id,eid,mid,sha,amount))
    return read(store,int(close_id))


def _verify_close(con, close_id: int) -> dict:
    """Validate the immutable period chain without rewriting old records."""
    checked=set()
    chain=[]
    cursor=close_id
    while cursor is not None:
        if cursor in checked:
            raise ValueError('결산 기간 연결에서 순환 참조가 발견됐습니다.')
        checked.add(cursor)
        row=con.execute('''SELECT business_id,cutoff_event_id,accepted_count,
            accepted_net_minor,owner_note,statement_sha256
            FROM aiwack_business_financial_closes WHERE id=?''',(cursor,)).fetchone()
        if row is None:raise ValueError('결산 기록 없음 또는 이전 결산 손실')
        period=con.execute('''SELECT period_start_event_id,previous_close_id,
             previous_statement_sha256,statement_version
             FROM aiwack_business_financial_close_periods WHERE close_id=?''',(cursor,)).fetchone()
        chain.append((cursor,row,period))
        cursor=period[1] if period else None
    previous_id=None
    previous_row=None
    previous_digest=None
    report=None
    for current_id,row,period in reversed(chain):
        business,cutoff,count,net,note,digest=row
        if period:
            start,prior,prior_hash,version=period
            if version!=2 or start<=0 or start>cutoff:
                raise ValueError('결산 기간 스키마·범위 손상')
            if prior!=previous_id or prior_hash!=(previous_digest or ''):
                raise ValueError('결산 기간 이전 해시 연결 무결성 오류')
            if previous_row and (previous_row[0]!=business or previous_row[1]+1!=start):
                raise ValueError('결산 기간 중복 또는 사업 불일치')
        else:
            start=1
            if previous_id is not None:
                raise ValueError('기존 결산과 기간 연결이 혼합됐습니다.')
        ready,blocked=_rows(con,business,cutoff,start=start)
        saved=con.execute('''SELECT payment_event_id,bank_match_id,event_sha256,amount_minor
            FROM aiwack_business_financial_close_lines
            WHERE close_id=? ORDER BY payment_event_id''',(current_id,)).fetchall()
        linked=[(eid,mid,sha,amount) for eid,mid,sha,amount in saved]
        expected=[(eid,mid,sha,amount) for eid,mid,sha,_kind,amount in ready]
        statement=_statement(business,cutoff,ready,note,
            period_start=start if period else None,
            previous=(previous_id,previous_row[1],previous_digest) if previous_id is not None else None)
        if (blocked or len(ready)!=count or net!=statement['net_minor']
                or linked!=expected or _digest(statement)!=digest):
            raise ValueError('결산 원문·기간·연결 거래 또는 과거 승인 내역의 무결성 오류')
        report={'id':current_id,'statement':statement,'statement_sha256':digest,
                'immutable_sqlite_close_verified':True,
                'bank_provider_independent_confirmation':False}
        previous_id=current_id;previous_row=row;previous_digest=digest
    return report


def read(store,close_id:int)->dict:
    store.require_permission('company:manage')
    if type(close_id) is not int or close_id<=0:
        raise ValueError('결산 조회 번호 오류')
    with store._connect() as con:
        initialize(con)
        return _verify_close(con,close_id)


def history(store, business_id: int) -> dict:
    """Read non-overlapping locally reconciled periods and running totals."""
    store.require_permission('company:manage')
    if type(business_id) is not int or business_id<=0:
        raise ValueError('사업 번호는 양의 정수여야 합니다.')
    with store._connect() as con:
        initialize(con)
        if not con.execute('SELECT 1 FROM managed_businesses WHERE id=?',(business_id,)).fetchone():
            raise ValueError('사업 기록 없음')
        ids=[row[0] for row in con.execute('''SELECT id FROM aiwack_business_financial_closes
            WHERE business_id=? ORDER BY cutoff_event_id,id''',(business_id,)).fetchall()]
        running=0
        entries=[]
        for close_id in ids:
            verified=_verify_close(con,close_id)
            statement=verified['statement']
            if statement.get('statement_version')==2:
                running+=statement['net_minor']
            else:
                running=statement['net_minor']
            entries.append({'close_id':close_id,
                'period_start_event_id':statement.get('period_start_event_id',1),
                'cutoff_event_id':statement['cutoff_event_id'],
                'statement_version':statement.get('statement_version',1),
                'accepted_count':statement['accepted_count'],
                'period_net_minor':statement['net_minor'] if statement.get('statement_version')==2 else None,
                'running_net_minor':running,
                'statement_sha256':verified['statement_sha256']})
    return {'business_id':business_id,'periods':entries,
            'cumulative_local_reconciled_net_minor':running,
            'local_bank_csv_only':True,'independent_bank_or_provider_verified':False,
            'actual_transfer_performed':False}
