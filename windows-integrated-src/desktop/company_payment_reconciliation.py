"""서명된 외부 거래 증빙: 중복/환불 대사와 관리자 검수. 공급자 독립 검증 미완료.

단순 서명 확인으로 실제 결제·은행 입금을 주장하지 않는다. 승인 없이 결제/환불하지 않는다.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import re
from desktop.stage87_90_management import stopped

VALID=frozenset({'settlement','refund','expense'})
KEY=re.compile(r'[a-zA-Z0-9._:-]{4,100}\Z')

def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_provider_payment_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,event_id TEXT NOT NULL,transaction_id TEXT NOT NULL,
        business_id INTEGER NOT NULL REFERENCES managed_businesses(id) ON DELETE RESTRICT,
        event_type TEXT NOT NULL CHECK(event_type IN ('settlement','refund','expense')),
        related_transaction TEXT NOT NULL DEFAULT '',
        currency TEXT NOT NULL CHECK(currency='KRW'),
        amount_minor INTEGER NOT NULL CHECK(amount_minor>0 AND amount_minor<=1000000000000),
        event_sha256 TEXT NOT NULL CHECK(length(event_sha256)=64),
        authenticated INTEGER NOT NULL CHECK(authenticated=1),
        owner_decision TEXT NOT NULL DEFAULT 'pending'
          CHECK(owner_decision IN ('pending','accepted','rejected')),
        decision_note TEXT NOT NULL DEFAULT '',received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        decided_at TEXT,UNIQUE(provider,event_id))""")
    con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_payment_no_delete
         BEFORE DELETE ON aiwack_provider_payment_events BEGIN
         SELECT RAISE(ABORT,'거래 증빙 삭제 금지'); END""")
    con.execute('CREATE INDEX IF NOT EXISTS aiwack_payment_by_business ON aiwack_provider_payment_events(business_id,id)')

def _ident(value):
    if type(value) is not int or value<=0: raise ValueError('사업/거래 ID는 양의 정수여야 합니다.')
    return value

def _key(value):
    if not isinstance(value,str) or not KEY.fullmatch(value):raise ValueError('외부 거래 번호 형식 오류')
    return value

def ingest(store,raw:bytes,signature:str,shared_secret:str):
    """공급자 공유 비밀키로 수신 원문 HMAC 확인. 실제 거래의 독립 검증은 별도."""
    store.require_permission('company:manage')
    if not isinstance(raw,bytes) or not 20<=len(raw)<=8192:raise ValueError('거래 JSON 크기 제한')
    if not isinstance(shared_secret,str) or not 20<=len(shared_secret)<=256:
        raise ValueError('공급자 발행 서명 확인 비밀키가 필요합니다.')
    if not isinstance(signature,str) or not re.fullmatch('[0-9a-fA-F]{64}',signature):
        raise ValueError('SHA256 서명이 필요합니다.')
    expected=hmac.new(shared_secret.encode(),raw,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,signature.lower()):
        raise PermissionError('거래 제공자 서명 확인 실패')
    try:payload=json.loads(raw.decode('utf8'))
    except (ValueError,UnicodeDecodeError) as exc:raise ValueError('거래 JSON 파싱 실패') from exc
    expected_keys={'provider','event_id','transaction_id','business_id','event_type',
                   'related_transaction','currency','amount_minor'}
    if not isinstance(payload,dict) or set(payload)!=expected_keys:
        raise ValueError('거래 증빙 스키마 불일치')
    provider=_key(payload['provider']);event=_key(payload['event_id'])
    tx=_key(payload['transaction_id']);business=_ident(payload['business_id'])
    kind=payload['event_type'];amount=payload['amount_minor'];related=payload['related_transaction']
    if kind not in VALID or payload['currency']!='KRW' or type(amount) is not int or not 0<amount<=10**12:
        raise ValueError('거래 유형/원화 금액이 올바르지 않습니다.')
    if (kind=='refund' and (not related or not KEY.fullmatch(related))) or (kind!='refund' and related!=''):
        raise ValueError('환불은 유효한 원거래 번호가 필요합니다.')
    digest=hashlib.sha256(raw).hexdigest()
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE');initialize(con)
        if stopped(con):raise PermissionError('비상정지 중 거래 수신 금지')
        if not con.execute('SELECT 1 FROM managed_businesses WHERE id=?',(business,)).fetchone():
            raise ValueError('존재하지 않는 사업')
        prior=con.execute('SELECT id,event_sha256 FROM aiwack_provider_payment_events WHERE provider=? AND event_id=?',
                          (provider,event)).fetchone()
        if prior:
            if prior[1]!=digest:raise ValueError('동일 이벤트 번호 내용 불일치')
            return {'id':int(prior[0]),'duplicate':True,'provider_verified':False}
        rid=con.execute("""INSERT INTO aiwack_provider_payment_events
            (provider,event_id,transaction_id,business_id,event_type,related_transaction,
             currency,amount_minor,event_sha256,authenticated) VALUES(?,?,?,?,?,?,?,?,?,1)""",
             (provider,event,tx,business,kind,related,'KRW',amount,digest)).lastrowid
    return {'id':int(rid),'duplicate':False,'state':'pending','provider_verified':False}

def review(store,event_id:int,decision:str,note:str):
    store.require_permission('company:manage');_ident(event_id)
    if decision not in ('accepted','rejected'):raise ValueError('수락·반려만 가능합니다.')
    if not isinstance(note,str) or not 5<=len(note.strip())<=200:raise ValueError('검수 사유 5~200자')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE');initialize(con)
        if stopped(con):raise PermissionError('비상정지 중 거래 승인 금지')
        row=con.execute('''SELECT provider,transaction_id,business_id,event_type,
            related_transaction,amount_minor,owner_decision
            FROM aiwack_provider_payment_events WHERE id=?''',(event_id,)).fetchone()
        if row is None:raise ValueError('없는 거래 이벤트')
        provider,tx,business,kind,related,amount,state=row
        if state!='pending':raise ValueError('이미 검수한 거래의 재승인 금지')
        if decision=='accepted' and kind=='refund':
            original=con.execute('''SELECT SUM(amount_minor) FROM aiwack_provider_payment_events
                WHERE provider=? AND transaction_id=? AND business_id=? AND event_type='settlement'
                  AND owner_decision='accepted' ''',(provider,related,business)).fetchone()[0] or 0
            refunded=con.execute('''SELECT SUM(amount_minor) FROM aiwack_provider_payment_events
                WHERE provider=? AND related_transaction=? AND business_id=? AND event_type='refund'
                  AND owner_decision='accepted' ''',(provider,related,business)).fetchone()[0] or 0
            if not original or refunded+amount>original:
                raise ValueError('검수된 원거래 금액을 초과하는 환불 금지')
        if decision=='accepted' and kind=='settlement':
            if con.execute('''SELECT 1 FROM aiwack_provider_payment_events
                WHERE provider=? AND transaction_id=? AND business_id=? AND event_type='settlement'
                 AND owner_decision='accepted' ''',(provider,tx,business)).fetchone():
                raise ValueError('같은 정산 거래를 두 번 승인할 수 없습니다.')
        con.execute('''UPDATE aiwack_provider_payment_events SET owner_decision=?,decision_note=?,
            decided_at=CURRENT_TIMESTAMP WHERE id=? AND owner_decision='pending' ''',
            (decision,note.strip(),event_id))
    return {'id':event_id,'decision':decision,'independent_provider_verification':False}

def summary(store,business_id:int|None=None):
    store.require_permission('company:manage')
    if business_id is not None:_ident(business_id)
    with store._connect() as con:
        initialize(con)
        rows=con.execute('''SELECT event_type,owner_decision,amount_minor
             FROM aiwack_provider_payment_events'''+(' WHERE business_id=?' if business_id else ''),
             ((business_id,) if business_id else ())).fetchall()
    total={'settlement':0,'refund':0,'expense':0}
    for kind,state,amount in rows:
        if state=='accepted':total[kind]+=amount
    return {'accepted_signed_settlements_minor':total['settlement'],
            'accepted_signed_refunds_minor':total['refund'],
            'accepted_signed_expenses_minor':total['expense'],
            'accepted_signed_net_minor':total['settlement']-total['refund']-total['expense'],
            'events':len(rows),'pending':sum(s=='pending' for k,s,a in rows),
            'currency':'KRW','real_bank_settlement_confirmed':False,
            'external_provider_connected':False,'independent_provider_verified':False}

def pending_events(store,limit:int=30):
    store.require_permission('company:manage')
    if type(limit) is not int or not 1<=limit<=100:raise ValueError('조회 범위 초과')
    with store._connect() as con:
        initialize(con)
        rows=con.execute('''SELECT id,provider,event_id,business_id,event_type,amount_minor,owner_decision
          FROM aiwack_provider_payment_events ORDER BY id DESC LIMIT ?''',(limit,)).fetchall()
    return [dict(id=i,provider=p,event_id=e,business_id=b,kind=k,amount_minor=a,state=s)
            for i,p,e,b,k,a,s in rows]
