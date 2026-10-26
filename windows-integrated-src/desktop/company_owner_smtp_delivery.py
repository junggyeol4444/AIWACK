"""Owner-commanded real SMTP transfer of previously approved AIWACK ZIP.

Optional service: AIWACK runs entirely locally without an SMTP account.
Credentials are accepted only in memory for one explicit owner-clicked send.
Only SMTP server acceptance is recorded, NEVER verified inbox delivery or pay.
No automatic retries after a timeout/crash and no overwrite of model output.
"""
from __future__ import annotations

from email.message import EmailMessage
from email.utils import make_msgid
import hashlib
import re
import smtplib
import ssl
from pathlib import Path
from uuid import uuid4

from desktop.stage87_90_management import stopped

_MAIL_RE=re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+\Z")
_HOST_RE=re.compile(r"(?=.{1,253}\Z)[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?\Z")


def _email(value):
    if not isinstance(value,str) or len(value)>254 or not _MAIL_RE.fullmatch(value):
        raise ValueError("관리자가 지정한 실제 발신/수신 이메일 주소 형식 오류")
    return value


def _host(value):
    if not isinstance(value,str) or not _HOST_RE.fullmatch(value) or ".." in value:
        raise ValueError("SMTP 서버 호스트 이름 형식 오류")
    return value


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_smtp_customer_deliveries(
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       handoff_id INTEGER NOT NULL UNIQUE
           REFERENCES aiwack_real_release_order_handoffs(id),
       order_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_local_order_intakes(id),
       release_id INTEGER NOT NULL REFERENCES aiwack_actual_model_releases(id),
       owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
       smtp_host TEXT NOT NULL,
       smtp_port INTEGER NOT NULL CHECK(smtp_port BETWEEN 1 AND 65535),
       sender TEXT NOT NULL,
       recipient TEXT NOT NULL,
       message_id TEXT NOT NULL UNIQUE,
       release_sha256 TEXT NOT NULL CHECK(length(release_sha256)=64),
       status TEXT NOT NULL CHECK(status IN
            ('claimed','accepted_by_smtp','not_sent','outcome_unknown')),
       error_kind TEXT NOT NULL DEFAULT '',
       claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
       finished_at TEXT
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_smtp_delivery_events(
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       delivery_id INTEGER NOT NULL REFERENCES aiwack_smtp_customer_deliveries(id),
       kind TEXT NOT NULL CHECK(kind IN
           ('owner_claimed','smtp_accepted','not_sent','outcome_unknown')),
       evidence TEXT NOT NULL DEFAULT '',
       created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
       UNIQUE(delivery_id,kind)
    )""")
    for op in ("UPDATE","DELETE"):
        con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_smtp_delivery_events_no_%s
            BEFORE %s ON aiwack_smtp_delivery_events
            BEGIN SELECT RAISE(ABORT,'SMTP 발송 원본 감사 삭제·수정 금지'); END"""
            %(op.lower(),op))


def _source(store,handoff_id):
    from desktop.company_real_release_order_handoff import read as handoff
    from desktop.company_actual_release_bundles import read as release_read
    prior=handoff(store,handoff_id)
    if not prior["current_owner_delivery_ready"]:
        raise PermissionError("실제 주문이 취소/환불됐거나 로컬 상품 준비가 미승인입니다")
    product=release_read(store,prior["release_id"])
    if prior["release_sha256"]!=product["sha256"]:
        raise PermissionError("실 GGUF 상품 ZIP 원본 SHA256 불일치")
    root=Path(product["path"])
    if root.is_symlink() or not root.is_file() or root.suffix.lower()!=".zip":
        raise PermissionError("관리자 승인 AI 제품 ZIP 원본 누락")
    binary=root.read_bytes()
    if not 1<=len(binary)<=1024*1024 or hashlib.sha256(binary).hexdigest()!=product["sha256"]:
        raise PermissionError("전송 직전 실제 승인 GGUF ZIP SHA256 불일치")
    return prior,product,binary


def _event(con,delivery_id,kind,reason=""):
    con.execute("""INSERT INTO aiwack_smtp_delivery_events
      (delivery_id,kind,evidence) VALUES(?,?,?)""",
      (delivery_id,kind,reason[:120]))


def deliver(store,handoff_id,host,port,sender,recipient,username,password,owner_note):
    """Exactly one explicitly authorized send attempt; password never stored."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if type(handoff_id) is not int or handoff_id<1:
        raise ValueError("로컬 AI 상품 주문 연결 번호 오류")
    smtp_host=_host(host)
    if type(port) is not int or port!=465:
        raise PermissionError("검증된 TLS SMTP_SSL 465 포트만 실제 고객 발송 허용")
    from_email=_email(sender)
    to_email=_email(recipient)
    if (not isinstance(username,str) or not 1<=len(username)<=254
            or "\r" in username or "\n" in username):
        raise ValueError("SMTP 계정 이름 형식 오류")
    if not isinstance(password,str) or not password or len(password)>4096:
        raise PermissionError("발송할 때만 사용할 일회성 SMTP 비밀번호가 필요합니다")
    if type(owner_note) is not str or not 5<=len(owner_note.strip())<=200:
        raise ValueError("고객 실제 발송 관리자 승인 사유 5~200자")
    proof,product,binary=_source(store,handoff_id)
    message_id=make_msgid(idstring=uuid4().hex,domain=from_email.split("@",1)[1])
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상 정지 중 실제 고객 이메일 발송 차단")
        if con.execute("""SELECT 1 FROM aiwack_smtp_customer_deliveries
            WHERE handoff_id=? OR order_id=?""",
            (handoff_id,proof["order_id"])).fetchone():
            raise PermissionError("이 주문의 이전 전송 시도가 있어 재발송하지 않습니다")
        from desktop.company_real_release_order_handoff import _source as live_source
        live=live_source(con,proof["order_id"],proof["release_id"],proof["packet_id"])
        if live["release_sha256"]!=product["sha256"]:
            raise PermissionError("원본 주문/상품 SHA256 변경")
        delivery_id=int(con.execute("""INSERT INTO aiwack_smtp_customer_deliveries(
            handoff_id,order_id,release_id,owner_note,smtp_host,smtp_port,
            sender,recipient,message_id,release_sha256,status)
            VALUES(?,?,?,?,?,?,?,?,?,?,'claimed')""",
            (handoff_id,proof["order_id"],proof["release_id"],owner_note.strip(),
             smtp_host,port,from_email,to_email,message_id,product["sha256"])).lastrowid)
        _event(con,delivery_id,"owner_claimed","서버 접속 전 단일 발송 시도 소유자 승인")
    phase="before_connection"
    state="outcome_unknown"
    error_kind=""
    accepted=False
    try:
        latest,latest_product,fresh_binary=_source(store,handoff_id)
        if latest["order_id"]!=proof["order_id"] or latest_product["sha256"]!=product["sha256"] or fresh_binary!=binary:
            raise PermissionError("네트워크 발송 직전 주문/제품 원본 변경")
        mail=EmailMessage()
        mail["From"]=from_email
        mail["To"]=to_email
        mail["Subject"]="AIWACK 승인 상품 전달 | 주문 "+str(proof["order_id"])
        mail["Message-ID"]=message_id
        mail.set_content("관리자가 검토·승인한 로컬 AIWACK 상품 파일을 첨부합니다.\n"
                         "이 이메일만으로 입금·은행 정산을 증명하지 않습니다.\n")
        mail.add_attachment(binary,maintype="application",subtype="zip",
                            filename="AIWACK_approved_product.zip")
        phase="connection_started"
        with smtplib.SMTP_SSL(smtp_host,port,timeout=25,
                             context=ssl.create_default_context()) as smtp:
            phase="authentication"
            smtp.login(username,password)
            phase="message_sending"
            refused=smtp.send_message(mail,from_addr=from_email,to_addrs=[to_email])
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
            phase="smtp_accepted"
            accepted=True
        state="accepted_by_smtp"
    except (smtplib.SMTPException,OSError,ValueError,PermissionError) as exc:
        error_kind=type(exc).__name__[:70]
        state=("not_sent" if phase in
               ("before_connection","connection_started","authentication")
               else "outcome_unknown")
        if phase=="smtp_accepted":
            state="accepted_by_smtp"
    finally:
        with store._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("""UPDATE aiwack_smtp_customer_deliveries
                SET status=?,error_kind=?,finished_at=CURRENT_TIMESTAMP
                WHERE id=? AND status='claimed'""",
                (state,error_kind,delivery_id)).rowcount:
                _event(con,delivery_id,
                       "smtp_accepted" if state=="accepted_by_smtp" else state,
                       error_kind)
    return {"delivery_id":delivery_id,"order_id":proof["order_id"],
            "smtp_status":state,"smtp_accepted":accepted,
            "recipient":to_email,"message_id":message_id,
            "error_kind":error_kind,
            "recipient_received_verified":False,
            "actual_payment_or_bank_verified":False,
            "secret_persisted":False,"automatic_retry":False}


def history(store,limit=30):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("실제 고객 SMTP 전달 이력 1~100건")
    with store._connect() as con:
        initialize(con)
        rows=con.execute("""SELECT id,handoff_id,order_id,release_id,smtp_host,
            sender,recipient,message_id,release_sha256,status,error_kind,
            claimed_at,finished_at FROM aiwack_smtp_customer_deliveries
            ORDER BY id DESC LIMIT ?""",(limit,)).fetchall()
    fields=("id","handoff_id","order_id","release_id","smtp_host",
            "sender","recipient","message_id","release_sha256","status",
            "error_kind","claimed_at","finished_at")
    return [{"receipt":dict(zip(fields,row)),
             "recipient_received_verified":False,
             "real_bank_or_pg_payment_verified":False,
             "credential_saved":False} for row in rows]
