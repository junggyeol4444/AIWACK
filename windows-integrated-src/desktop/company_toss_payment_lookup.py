"""Owner-initiated read-only Toss Payments GET verification for an existing HMAC event.

Official API: GET https://api.tosspayments.com/v1/payments/{paymentKey}
Authorization: Basic base64(secret_key + ":"). No POST, cancel, settlement
creation, merchant enrollment, account changes, or background network work.
A real provider response verifies only payment status at lookup time, never
bank deposit, payout, customer delivery, or future chargeback status.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import (Request, HTTPSHandler, HTTPRedirectHandler,
                            ProxyHandler, build_opener)

from desktop import company_payment_reconciliation as payments
from desktop.stage87_90_management import stopped

HOST="https://api.tosspayments.com"
PAYMENT_KEY=re.compile(r"[A-Za-z0-9_-]{6,100}\Z")
ORDER_ID=re.compile(r"[A-Za-z0-9_-]{6,64}\Z")
MAX_RESPONSE=131072
_ALLOWED_SECRET_PREFIX=("test_sk_","test_gsk_","live_sk_","live_gsk_")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        return None


def _id(value):
    if type(value) is not int or value<=0:
        raise ValueError("서명 결제 원본 ID는 양의 정수여야 합니다")
    return value


def _key(value):
    if not isinstance(value,str) or not PAYMENT_KEY.fullmatch(value):
        raise ValueError("토스페이먼츠 paymentKey 형식 오류 (6~100자)")
    return value


def _order(value):
    if not isinstance(value,str) or not ORDER_ID.fullmatch(value):
        raise ValueError("토스페이먼츠 원본 주문번호 형식 오류 (6~64자)")
    return value


def _secret(value):
    if (not isinstance(value,str) or not 16<=len(value)<=256
            or not value.startswith(_ALLOWED_SECRET_PREFIX)
            or any(ord(char)<33 or ord(char)>126 for char in value)):
        raise PermissionError("토스페이먼츠 테스트/운영 시크릿 키를 이번 조회에만 입력해야 합니다")
    return value


def initialize(con):
    payments.initialize(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_toss_payment_verifications(
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       payment_event_id INTEGER NOT NULL
           REFERENCES aiwack_provider_payment_events(id),
       payment_key_sha256 TEXT NOT NULL CHECK(length(payment_key_sha256)=64),
       expected_order_id TEXT NOT NULL,
       amount_minor INTEGER NOT NULL CHECK(amount_minor>0),
       owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
       key_environment TEXT NOT NULL CHECK(key_environment IN ('test','live')),
       status TEXT NOT NULL DEFAULT 'claimed'
           CHECK(status IN ('claimed','verified','mismatch','unavailable')),
       response_sha256 TEXT NOT NULL DEFAULT '',
       reason_code TEXT NOT NULL DEFAULT '',
       requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
       finished_at TEXT
    )""")
    con.execute("""CREATE UNIQUE INDEX IF NOT EXISTS aiwack_toss_single_verified
       ON aiwack_toss_payment_verifications(payment_event_id)
       WHERE status='verified'""")
    con.execute("""CREATE UNIQUE INDEX IF NOT EXISTS aiwack_toss_single_active
       ON aiwack_toss_payment_verifications(payment_event_id)
       WHERE status='claimed'""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_toss_payment_verification_events(
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       attempt_id INTEGER NOT NULL REFERENCES aiwack_toss_payment_verifications(id),
       kind TEXT NOT NULL CHECK(kind IN
          ('owner_claimed','api_verified','api_mismatch','api_unavailable')),
       reason_code TEXT NOT NULL DEFAULT '',
       created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
       UNIQUE(attempt_id,kind)
    )""")
    con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_toss_verification_no_delete
        BEFORE DELETE ON aiwack_toss_payment_verifications
        BEGIN SELECT RAISE(ABORT,'실 PG 조회 감사 삭제 금지'); END""")
    con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_toss_verification_guard_update
        BEFORE UPDATE ON aiwack_toss_payment_verifications
        WHEN OLD.status!='claimed' OR NEW.status='claimed'
          OR NEW.id!=OLD.id OR NEW.payment_event_id!=OLD.payment_event_id
          OR NEW.payment_key_sha256!=OLD.payment_key_sha256
          OR NEW.expected_order_id!=OLD.expected_order_id
          OR NEW.amount_minor!=OLD.amount_minor
          OR NEW.owner_note!=OLD.owner_note
          OR NEW.key_environment!=OLD.key_environment
          OR NEW.requested_at!=OLD.requested_at
          OR NEW.finished_at IS NULL
        BEGIN SELECT RAISE(ABORT,'실 PG 조회 원본 변경 금지'); END""")
    for action in ("UPDATE","DELETE"):
        con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_toss_event_no_%s
           BEFORE %s ON aiwack_toss_payment_verification_events
           BEGIN SELECT RAISE(ABORT,'실 PG 조회 이벤트 불변 감사'); END"""
           %(action.lower(),action))


def _original(con,event_id,payment_key):
    row=con.execute("""SELECT provider,transaction_id,event_type,
        currency,amount_minor,authenticated,owner_decision,business_id
        FROM aiwack_provider_payment_events WHERE id=?""",(event_id,)).fetchone()
    if not row:
        raise ValueError("연결할 기존 HMAC 결제 이벤트가 없습니다")
    provider,tx,kind,currency,amount,authenticated,decision,business=row
    if provider!="tosspayments" or kind!="settlement":
        raise PermissionError("토스페이먼츠 정산 원본 이벤트만 조회할 수 있습니다")
    if tx!=payment_key or currency!="KRW" or authenticated!=1 or decision!="accepted":
        raise PermissionError("paymentKey와 원본 서명·관리자 승인 거래가 불일치합니다")
    if not 0<int(amount)<=10**12:
        raise ValueError("원본 승인 거래 금액 범위 오류")
    return {"payment_event_id":event_id,"business_id":int(business),
            "amount_minor":int(amount),"provider":"tosspayments",
            "event_approved":True}


def preview(store,event_id,payment_key,order_id):
    store.require_permission("company:manage")
    _id(event_id)
    _key(payment_key)
    _order(order_id)
    with store._connect() as con:
        initialize(con)
        item=_original(con,event_id,payment_key)
        verified=con.execute("""SELECT id FROM aiwack_toss_payment_verifications
          WHERE payment_event_id=? AND status='verified'""",(event_id,)).fetchone()
        active=con.execute("""SELECT id FROM aiwack_toss_payment_verifications
          WHERE payment_event_id=? AND status='claimed'""",(event_id,)).fetchone()
        bank=con.execute("""SELECT 1 FROM aiwack_bank_reconciliation_matches
          WHERE payment_event_id=?""",(event_id,)).fetchone() if _table_exists(
              con,"aiwack_bank_reconciliation_matches") else None
    return {**item,"expected_order_id":order_id,
            "payment_key_sha256":hashlib.sha256(payment_key.encode()).hexdigest(),
            "already_api_verified":bool(verified),"in_flight_or_unresolved":bool(active),
            "locally_bank_file_matched":bool(bank),
            "external_provider_lookup_performed":False,
            "actual_bank_deposit_verified":False,"read_only":True}


def _table_exists(con,name):
    return bool(con.execute("""SELECT 1 FROM sqlite_master
       WHERE type='table' AND name=?""",(name,)).fetchone())


def _read_payment(payment_key,secret):
    # Fixed destination; no user-provided host or path/URL and no redirects.
    url=HOST+"/v1/payments/"+payment_key
    token=base64.b64encode((secret+":").encode("ascii")).decode("ascii")
    request=Request(url,headers={"Authorization":"Basic "+token,
                                  "Accept":"application/json",
                                  "User-Agent":"AIWACK-local-owner-readonly/1.0"},
                    method="GET")
    opener=build_opener(ProxyHandler({}),HTTPSHandler(context=ssl.create_default_context()),
                        _NoRedirect())
    with opener.open(request,timeout=15) as response:
        if response.status!=200:
            raise ValueError("HTTP 상태가 200이 아닙니다")
        content_type=response.headers.get_content_type()
        if content_type!="application/json":
            raise ValueError("결제 제공자 JSON Content-Type 오류")
        raw=response.read(MAX_RESPONSE+1)
    if not 2<=len(raw)<=MAX_RESPONSE:
        raise ValueError("결제 제공자 응답 크기 제한")
    data=json.loads(raw.decode("utf-8"))
    if not isinstance(data,dict):
        raise ValueError("결제 제공자 응답 객체 형식 오류")
    return data,hashlib.sha256(raw).hexdigest()


def _classify(data,payment_key,order_id,amount):
    if data.get("paymentKey")!=payment_key:
        return "mismatch","payment_key"
    if data.get("orderId")!=order_id:
        return "mismatch","order_id"
    if data.get("currency")!="KRW":
        return "mismatch","currency"
    if type(data.get("totalAmount")) is not int or data["totalAmount"]!=amount:
        return "mismatch","amount"
    if data.get("status")!="DONE" or not isinstance(data.get("approvedAt"),str) or not data["approvedAt"]:
        return "mismatch","payment_not_done"
    if (type(data.get("balanceAmount")) is not int
            or data["balanceAmount"]!=amount or data.get("cancels") not in (None,[])):
        return "mismatch","refund_or_balance_changed"
    return "verified","payment_status_done"


def verify(store,event_id,payment_key,order_id,api_secret,owner_note):
    """Owner-approved real GET; never creates or cancels a charge."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    _id(event_id)
    _key(payment_key)
    _order(order_id)
    _secret(api_secret)
    if type(owner_note) is not str or not 5<=len(owner_note.strip())<=200:
        raise ValueError("관리자 실제 PG 조회 사유 5~200자")
    environment="live" if api_secret.startswith("live_") else "test"
    # Claim before network: concurrent same event and already-verified event
    # cannot be reverified as if a new independent settlement existed.
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상 정지 중 외부 PG 조회 금지")
        original=_original(con,event_id,payment_key)
        existing=con.execute("""SELECT status FROM aiwack_toss_payment_verifications
            WHERE payment_event_id=? AND status IN ('claimed','verified')
            LIMIT 1""",(event_id,)).fetchone()
        if existing:
            raise PermissionError("이미 조회 성공 또는 아직 종료되지 않은 PG 조회 시도가 있습니다")
        attempt_id=int(con.execute("""INSERT INTO aiwack_toss_payment_verifications(
            payment_event_id,payment_key_sha256,expected_order_id,amount_minor,
            key_environment,owner_note) VALUES(?,?,?,?,?,?)""",
            (event_id,hashlib.sha256(payment_key.encode()).hexdigest(),
             order_id,original["amount_minor"],environment,owner_note.strip())).lastrowid)
        con.execute("""INSERT INTO aiwack_toss_payment_verification_events
            (attempt_id,kind,reason_code) VALUES(?,'owner_claimed','manual_get_only')""",
            (attempt_id,))
    status="unavailable"
    reason="no_response"
    response_sha=""
    try:
        data,response_sha=_read_payment(payment_key,api_secret)
        status,reason=_classify(data,payment_key,order_id,original["amount_minor"])
    except (HTTPError,URLError,OSError,TimeoutError,ValueError,UnicodeError) as exc:
        # Never persist an exception message: URLs and response data may contain
        # secrets or customer information. Class name is enough for diagnostics.
        status="unavailable"
        reason=type(exc).__name__[:70]
    finally:
        with store._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            change=con.execute("""UPDATE aiwack_toss_payment_verifications
               SET status=?,reason_code=?,response_sha256=?,finished_at=CURRENT_TIMESTAMP
               WHERE id=? AND status='claimed'""",
               (status,reason,response_sha,attempt_id))
            if change.rowcount==1:
                con.execute("""INSERT INTO aiwack_toss_payment_verification_events
                    (attempt_id,kind,reason_code) VALUES(?,?,?)""",
                    (attempt_id,"api_"+("verified" if status=="verified" else
                         "mismatch" if status=="mismatch" else "unavailable"),reason))
    return {"attempt_id":attempt_id,"event_id":event_id,
            "status":status,"reason_code":reason,"environment":environment,
            "response_sha256":response_sha,
            "provider_payment_status_at_lookup_verified":status=="verified",
            "bank_deposit_verified":False,"future_refunds_or_chargebacks_checked":False,
            "external_payment_or_refund_executed":False,
            "secret_saved":False}


def history(store,limit=50):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=200:
        raise ValueError("토스 실제 조회 원본 조회 범위 1~200건")
    with store._connect() as con:
        initialize(con)
        rows=con.execute("""SELECT id,payment_event_id,payment_key_sha256,
            expected_order_id,amount_minor,owner_note,key_environment,status,
            response_sha256,reason_code,requested_at,finished_at
            FROM aiwack_toss_payment_verifications
            ORDER BY id DESC LIMIT ?""",(limit,)).fetchall()
    fields=("id","payment_event_id","payment_key_sha256","expected_order_id",
            "amount_minor","owner_note","environment","status","response_sha256",
            "reason_code","requested_at","finished_at")
    return [{"original":dict(zip(fields,row)),"secret_saved":False,
             "bank_settlement_verified":False,"no_payment_mutation":True}
            for row in rows]
