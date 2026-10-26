"""Owner-approved Toss Payments one-shot real cancellation (full/partial).

Optional Windows-local API integration. Nothing runs automatically or at
startup. Only the authenticated owner may explicitly approve a refund.
A claimed refund attempt is never retried after crash, timeout or mismatch.
The immutable local ledger distinguishes provider cancellation acceptance from
actual bank refund, payout, or customer account receipt.
Official contract: POST /v1/payments/{paymentKey}/cancel with Idempotency-Key.
Virtual accounts, escrow, tax-free and pre-partially-cancelled payments are
intentionally NOT eligible for this first direct integration.
"""
from __future__ import annotations

import base64
import hashlib
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPSHandler, ProxyHandler, build_opener
from uuid import uuid4

from desktop import company_toss_payment_lookup as lookup
from desktop.stage87_90_management import stopped

_ALLOWED_METHODS={"카드","간편결제","CARD","EASY_PAY"}
_MAX_AMOUNT=10**12


def initialize(con):
    lookup.initialize(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_toss_owner_refund_attempts(
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       payment_event_id INTEGER NOT NULL UNIQUE
           REFERENCES aiwack_provider_payment_events(id),
       verification_id INTEGER NOT NULL
           REFERENCES aiwack_toss_payment_verifications(id),
       payment_key_sha256 TEXT NOT NULL CHECK(length(payment_key_sha256)=64),
       order_id TEXT NOT NULL,
       original_amount_minor INTEGER NOT NULL CHECK(original_amount_minor>0),
       cancel_amount_minor INTEGER NOT NULL CHECK(cancel_amount_minor>0),
       cancel_reason TEXT NOT NULL CHECK(length(cancel_reason) BETWEEN 5 AND 200),
       owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
       key_environment TEXT NOT NULL CHECK(key_environment IN ('test','live')),
       idempotency_key TEXT NOT NULL UNIQUE,
       state TEXT NOT NULL DEFAULT 'claimed'
          CHECK(state IN ('claimed','not_sent','accepted_by_provider','outcome_unknown')),
       preflight_response_sha256 TEXT NOT NULL DEFAULT '',
       post_response_sha256 TEXT NOT NULL DEFAULT '',
       cancel_transaction_sha256 TEXT NOT NULL DEFAULT '',
       error_kind TEXT NOT NULL DEFAULT '',
       created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
       finished_at TEXT
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_toss_owner_refund_events(
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       attempt_id INTEGER NOT NULL REFERENCES aiwack_toss_owner_refund_attempts(id),
       kind TEXT NOT NULL CHECK(kind IN
           ('owner_claimed','preflight_approved','post_started',
            'provider_accepted','not_sent','outcome_unknown')),
       evidence TEXT NOT NULL DEFAULT '',
       created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
       UNIQUE(attempt_id,kind)
    )""")
    con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_toss_owner_refund_no_delete
       BEFORE DELETE ON aiwack_toss_owner_refund_attempts
       BEGIN SELECT RAISE(ABORT,'실제 PG 취소 시도 원본 삭제 금지'); END""")
    con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_toss_owner_refund_guard_update
       BEFORE UPDATE ON aiwack_toss_owner_refund_attempts
       WHEN OLD.state!='claimed' OR NEW.state='claimed'
          OR NEW.id!=OLD.id OR NEW.payment_event_id!=OLD.payment_event_id
          OR NEW.verification_id!=OLD.verification_id
          OR NEW.payment_key_sha256!=OLD.payment_key_sha256
          OR NEW.order_id!=OLD.order_id
          OR NEW.original_amount_minor!=OLD.original_amount_minor
          OR NEW.cancel_amount_minor!=OLD.cancel_amount_minor
          OR NEW.cancel_reason!=OLD.cancel_reason
          OR NEW.owner_note!=OLD.owner_note
          OR NEW.key_environment!=OLD.key_environment
          OR NEW.idempotency_key!=OLD.idempotency_key
          OR NEW.created_at!=OLD.created_at OR NEW.finished_at IS NULL
       BEGIN SELECT RAISE(ABORT,'실제 PG 취소 시도 원본 변경 금지'); END""")
    for action in ("UPDATE","DELETE"):
        con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_toss_owner_refund_event_no_%s
           BEFORE %s ON aiwack_toss_owner_refund_events
           BEGIN SELECT RAISE(ABORT,'실제 PG 취소 이벤트 변경·삭제 금지'); END"""
           %(action.lower(),action))


def _event(con,attempt_id,kind,evidence=""):
    con.execute("""INSERT INTO aiwack_toss_owner_refund_events
       (attempt_id,kind,evidence) VALUES(?,?,?)""",
       (attempt_id,kind,evidence[:100]))


def _original_verified(con,event_id,payment_key,order_id,environment):
    original=lookup._original(con,event_id,payment_key)
    verified=con.execute("""SELECT id,expected_order_id,amount_minor,
        payment_key_sha256,key_environment FROM aiwack_toss_payment_verifications
        WHERE payment_event_id=? AND status='verified'
        ORDER BY id DESC LIMIT 1""",(event_id,)).fetchone()
    expected_sha=hashlib.sha256(payment_key.encode("ascii")).hexdigest()
    if not verified or (verified[1],verified[2],verified[3])!=(
            order_id,original["amount_minor"],expected_sha):
        raise PermissionError("이 paymentKey·주문·금액의 기존 실제 PG 조회 성공 원본이 필요합니다")
    if environment is not None and verified[4]!=environment:
        raise PermissionError("PG 조회 성공 원본과 실제 환불 시크릿 키의 test/live 환경 불일치")
    return original,int(verified[0]),verified[4]


def _amount(value,original):
    if type(value) is not int or not 1<=value<=min(original,_MAX_AMOUNT):
        raise ValueError("실제 취소 원화 금액은 1원 이상·기존 승인 금액 이하여야 합니다")


def _reason(value,name):
    if (type(value) is not str or not 5<=len(value.strip())<=200
            or any(ord(c)<32 or ord(c)==127 for c in value)):
        raise ValueError(name+" 5~200자, 제어문자 금지")
    return value.strip()


def _prior(con,event_id):
    return con.execute("""SELECT id,state FROM aiwack_toss_owner_refund_attempts
        WHERE payment_event_id=?""",(event_id,)).fetchone()


def preview(store,event_id,payment_key,order_id,cancel_amount):
    """Local-only preview: never makes an HTTP request."""
    store.require_permission("company:manage")
    lookup._id(event_id)
    lookup._key(payment_key)
    lookup._order(order_id)
    with store._connect() as con:
        initialize(con)
        original,verification_id,environment=_original_verified(
            con,event_id,payment_key,order_id,None)
        _amount(cancel_amount,original["amount_minor"])
        previous=_prior(con,event_id)
    return {"event_id":event_id,"verification_id":verification_id,
            "order_id":order_id,"original_amount_minor":original["amount_minor"],
            "cancel_amount_minor":cancel_amount,
            "kind":"full" if cancel_amount==original["amount_minor"] else "partial",
            "verified_lookup_environment":environment,
            "previous_attempt_id":int(previous[0]) if previous else None,
            "previous_attempt_state":previous[1] if previous else None,
            "can_start_one_shot":previous is None,
            "required_confirmation":"환불확인:"+str(cancel_amount)+":"+payment_key[-6:],
            "external_api_called":False,"money_refunded":False}


def _preflight(data,payment_key,order_id,total,cancel_amount):
    status,reason=lookup._classify(data,payment_key,order_id,total)
    if status!="verified":
        raise PermissionError("실제 PG 현재 상태/주문/잔액 사전조회 불일치: "+reason)
    if data.get("method") not in _ALLOWED_METHODS:
        raise PermissionError("이번 버전은 카드/간편결제에 한하여 환불 가능")
    if data.get("virtualAccount") is not None or data.get("useEscrow") is not False:
        raise PermissionError("가상계좌·에스크로 환불은 계좌 정보 및 별도 승인 연동이 필요")
    if data.get("taxFreeAmount")!=0:
        raise PermissionError("면세·복합과세 환불은 별도 세금 검토 필요")
    _amount(cancel_amount,total)


def _post_cancel(payment_key,api_secret,reason,amount,idempotency_key):
    body=json.dumps({"cancelReason":reason,"cancelAmount":amount},
                    ensure_ascii=False,separators=(",",":")).encode("utf-8")
    token=base64.b64encode((api_secret+":").encode("ascii")).decode("ascii")
    req=Request(lookup.HOST+"/v1/payments/"+payment_key+"/cancel",data=body,
                headers={"Authorization":"Basic "+token,
                         "Content-Type":"application/json",
                         "Accept":"application/json",
                         "Idempotency-Key":idempotency_key,
                         "User-Agent":"AIWACK-owner-refund/1.0"},method="POST")
    opener=build_opener(ProxyHandler({}),
                        HTTPSHandler(context=ssl.create_default_context()),
                        lookup._NoRedirect())
    with opener.open(req,timeout=20) as response:
        if response.status!=200 or response.headers.get_content_type()!="application/json":
            raise ValueError("PG 취소 API HTTP/Content-Type 불일치")
        raw=response.read(lookup.MAX_RESPONSE+1)
    if not 2<=len(raw)<=lookup.MAX_RESPONSE:
        raise ValueError("PG 취소 API 응답 크기 제한")
    result=json.loads(raw.decode("utf-8"))
    if not isinstance(result,dict):
        raise ValueError("PG 취소 API JSON 객체 형식 오류")
    return result,hashlib.sha256(raw).hexdigest()


def _cancel_response(data,payment_key,order_id,total,amount):
    if (data.get("paymentKey")!=payment_key or data.get("orderId")!=order_id
            or data.get("currency")!="KRW" or type(data.get("totalAmount")) is not int
            or data["totalAmount"]!=total
            or type(data.get("balanceAmount")) is not int
            or data["balanceAmount"]!=total-amount
            or data.get("status")!=("CANCELED" if amount==total else "PARTIAL_CANCELED")):
        raise ValueError("PG 취소 응답 주문·잔액·취소상태 불일치")
    cancels=data.get("cancels")
    if not isinstance(cancels,list) or len(cancels)!=1 or not isinstance(cancels[0],dict):
        raise ValueError("PG 취소 응답 취소 거래 1건 확인 실패")
    item=cancels[0]
    if (item.get("cancelStatus")!="DONE" or
            type(item.get("cancelAmount")) is not int or
            item["cancelAmount"]!=amount or
            not isinstance(item.get("transactionKey"),str) or
            not 1<=len(item["transactionKey"])<=200):
        raise ValueError("PG 취소 거래 원본 상태·금액·식별자 불일치")
    return hashlib.sha256(item["transactionKey"].encode("utf-8")).hexdigest()


def cancel_once(store,event_id,payment_key,order_id,cancel_amount,api_secret,
                cancel_reason,owner_note,confirmation):
    """Owner-specific explicit irreversible external POST. NEVER auto-invoked."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    lookup._id(event_id)
    lookup._key(payment_key)
    lookup._order(order_id)
    lookup._secret(api_secret)
    reason=_reason(cancel_reason,"실제 PG 환불 사유")
    note=_reason(owner_note,"실제 PG 환불 소유자 승인 사유")
    if confirmation!="환불확인:"+str(cancel_amount)+":"+payment_key[-6:]:
        raise PermissionError("실제 환불 금액과 paymentKey 끝 6자리 확인 문구 불일치")
    environment="live" if api_secret.startswith("live_") else "test"
    # Persist a single irrevocable intent BEFORE the first network request.
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 외부 PG 환불 요청 금지")
        original,verification_id,_=_original_verified(
            con,event_id,payment_key,order_id,environment)
        total=original["amount_minor"]
        _amount(cancel_amount,total)
        if _prior(con,event_id):
            raise PermissionError("기존 환불 시도 원본 존재: 재시도 대신 공급자 관리자 조회 필요")
        idem=str(uuid4())
        attempt_id=int(con.execute("""INSERT INTO aiwack_toss_owner_refund_attempts(
            payment_event_id,verification_id,payment_key_sha256,order_id,
            original_amount_minor,cancel_amount_minor,cancel_reason,
            owner_note,key_environment,idempotency_key)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (event_id,verification_id,hashlib.sha256(payment_key.encode()).hexdigest(),
             order_id,total,cancel_amount,reason,note,environment,idem)).lastrowid)
        _event(con,attempt_id,"owner_claimed","관리자 환불확인 문구·금액 승인")
    phase="before_post"
    state="not_sent"
    error_kind=""
    preflight_sha=""
    post_sha=""
    cancel_tx_sha=""
    try:
        # Fresh provider GET after durable owner intent, before any refund POST.
        payment,preflight_sha=lookup._read_payment(payment_key,api_secret)
        _preflight(payment,payment_key,order_id,total,cancel_amount)
        with store._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if stopped(con):
                raise PermissionError("비상정지 중 환불 POST 출발 거부")
            _event(con,attempt_id,"preflight_approved","실 PG 최신 GET 결제 상태 일치")
            # Persist 'POST may start' BEFORE opening network connection.
            _event(con,attempt_id,"post_started","이후 실패는 실제 환불 여부 미확정")
        phase="post_may_have_started"
        result,post_sha=_post_cancel(payment_key,api_secret,reason,cancel_amount,idem)
        phase="post_response_received"
        cancel_tx_sha=_cancel_response(result,payment_key,order_id,total,cancel_amount)
        state="accepted_by_provider"
    except (HTTPError,URLError,OSError,TimeoutError,ValueError,
            PermissionError,UnicodeError) as exc:
        error_kind=type(exc).__name__[:70]
        state="not_sent" if phase=="before_post" else "outcome_unknown"
    finally:
        with store._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            updated=con.execute("""UPDATE aiwack_toss_owner_refund_attempts
                SET state=?,preflight_response_sha256=?,
                    post_response_sha256=?,cancel_transaction_sha256=?,
                    error_kind=?,finished_at=CURRENT_TIMESTAMP
                WHERE id=? AND state='claimed'""",
                (state,preflight_sha,post_sha,cancel_tx_sha,
                 error_kind,attempt_id)).rowcount
            if updated==1:
                _event(con,attempt_id,
                       "provider_accepted" if state=="accepted_by_provider" else state,
                       "PG 응답 대조 완료" if state=="accepted_by_provider" else error_kind)
    return {"attempt_id":attempt_id,"payment_event_id":event_id,
            "cancel_amount_minor":cancel_amount,"state":state,
            "environment":environment,"preflight_response_sha256":preflight_sha,
            "post_response_sha256":post_sha,"cancel_transaction_sha256":cancel_tx_sha,
            "error_kind":error_kind,
            "provider_cancel_response_verified":state=="accepted_by_provider",
            "bank_refund_received_verified":False,
            "customer_account_credit_verified":False,
            "automatic_retry":False,"api_secret_saved":False}


def history(store,limit=30):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("토스 실제 취소 시도 감사 조회 1~100건")
    with store._connect() as con:
        initialize(con)
        rows=con.execute("""SELECT id,payment_event_id,verification_id,
            payment_key_sha256,order_id,original_amount_minor,cancel_amount_minor,
            key_environment,idempotency_key,state,preflight_response_sha256,
            post_response_sha256,cancel_transaction_sha256,error_kind,
            created_at,finished_at FROM aiwack_toss_owner_refund_attempts
            ORDER BY id DESC LIMIT ?""",(limit,)).fetchall()
    names=("id","payment_event_id","verification_id","payment_key_sha256",
           "order_id","original_amount_minor","cancel_amount_minor",
           "key_environment","idempotency_key","state",
           "preflight_response_sha256","post_response_sha256",
           "cancel_transaction_sha256","error_kind","created_at","finished_at")
    return [{**dict(zip(names,row)),
             "bank_refund_received_verified":False,
             "customer_account_credit_verified":False,
             "automatic_retry":False} for row in rows]
