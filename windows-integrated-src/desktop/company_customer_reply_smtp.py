"""실제 승인된 고객지원 직원/총괄 결과를 관리자 직접 승인으로 SMTP 발송.

고객의 실제 수령·은행 입금·GGUF 바이너리 검증은 주장하지 않는다.
발송 시도는 문의당 한 번만 허용하며 결과 불명/실패 후 자동 재시도하지 않는다.
SMTP 비밀번호는 함수 메모리에서만 사용하고 DB·감사에 저장하지 않는다.
"""
from __future__ import annotations

from email.message import EmailMessage
from email.utils import make_msgid
import hashlib
import smtplib
import ssl
from uuid import uuid4

from desktop import company_customer_cases as cases
from desktop.company_owner_smtp_delivery import _email, _host
from desktop.stage87_90_management import stopped


def initialize(con):
    cases.initialize(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_customer_reply_smtp_attempts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_customer_cases(id),
        artifact_id INTEGER NOT NULL REFERENCES company_task_artifacts(id),
        reply_sha256 TEXT NOT NULL CHECK(length(reply_sha256)=64),
        sender TEXT NOT NULL,
        recipient TEXT NOT NULL,
        smtp_host TEXT NOT NULL,
        message_id TEXT NOT NULL UNIQUE,
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        status TEXT NOT NULL CHECK(status IN
            ('claimed','accepted_by_smtp','not_sent','outcome_unknown')),
        error_kind TEXT NOT NULL DEFAULT '',
        claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at TEXT
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_customer_reply_smtp_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        attempt_id INTEGER NOT NULL REFERENCES aiwack_customer_reply_smtp_attempts(id),
        kind TEXT NOT NULL CHECK(kind IN
            ('owner_claimed','smtp_accepted','not_sent','outcome_unknown')),
        detail TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(attempt_id,kind)
    )""")
    for operation in ("UPDATE", "DELETE"):
        con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_reply_smtp_event_no_%s
            BEFORE %s ON aiwack_customer_reply_smtp_events
            BEGIN SELECT RAISE(ABORT,'고객지원 SMTP 원본 감사 변경 금지'); END"""
            % (operation.lower(), operation))
    con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_reply_smtp_attempt_no_delete
        BEFORE DELETE ON aiwack_customer_reply_smtp_attempts
        BEGIN SELECT RAISE(ABORT,'고객지원 SMTP 시도 삭제 금지'); END""")
    con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_reply_smtp_attempt_update_guard
        BEFORE UPDATE ON aiwack_customer_reply_smtp_attempts
        WHEN OLD.status!='claimed'
          OR NEW.status NOT IN ('accepted_by_smtp','not_sent','outcome_unknown')
          OR NEW.case_id!=OLD.case_id OR NEW.artifact_id!=OLD.artifact_id
          OR NEW.reply_sha256!=OLD.reply_sha256 OR NEW.sender!=OLD.sender
          OR NEW.recipient!=OLD.recipient OR NEW.smtp_host!=OLD.smtp_host
          OR NEW.message_id!=OLD.message_id OR NEW.owner_note!=OLD.owner_note
          OR NEW.claimed_at!=OLD.claimed_at
          OR NEW.finished_at IS NULL
        BEGIN SELECT RAISE(ABORT,'SMTP 원본 상태 전이 외 변경 금지'); END""")


def _approved_reply(store, case_id):
    if type(case_id) is not int or case_id <= 0:
        raise ValueError("고객지원 문의 번호 오류")
    case = cases.read(store, case_id)
    if (case["state"] not in ("response_ready", "closed")
            or not case["chief_model_call_audited"]
            or not case["artifact_id"]):
        raise PermissionError("직원 결과·총괄 모델 감사·관리자 승인 고객지원 답변만 발송 가능")
    with store._connect() as con:
        row = con.execute("""SELECT body FROM company_task_artifacts
            WHERE id=? AND task_id=? AND review_status='approved'""",
            (case["artifact_id"], case["task_id"])).fetchone()
    if not row or not isinstance(row[0], str):
        raise ValueError("승인된 고객지원 결과 원문이 없습니다")
    body = row[0]
    if (not body.strip() or len(body.encode("utf-8")) > 65536
            or hashlib.sha256(body.encode("utf-8")).hexdigest()
            != case["reply_sha256"]):
        raise ValueError("고객지원 원문 SHA256/크기 검증 실패")
    return case, body


def preview(store, case_id):
    """소유자 읽기 전용 검토: 실제 발송은 절대로 수행하지 않는다."""
    store.require_permission("company:manage")
    case, body = _approved_reply(store, case_id)
    with store._connect() as con:
        initialize(con)
        prior = con.execute("""SELECT id,status,recipient FROM
            aiwack_customer_reply_smtp_attempts WHERE case_id=?""",
            (case_id,)).fetchone()
    return {
        "case_id": case_id, "case_ref": case["case_ref"],
        "artifact_id": case["artifact_id"],
        "reply_sha256": case["reply_sha256"],
        "owner_confirmation_prefix": case["reply_sha256"][:12],
        "approved_reply_full_text": body,
        "previous_attempt": (dict(id=prior[0],status=prior[1],
                                  recipient=prior[2]) if prior else None),
        "send_allowed_if_explicitly_approved": prior is None,
        "chief_model_call_audited": True,
        "actual_gguf_binary_independently_verified": False,
        "customer_message_sent": False,
        "external_request_performed": False
    }


def _event(con, attempt_id, kind, detail=""):
    con.execute("""INSERT INTO aiwack_customer_reply_smtp_events
        (attempt_id,kind,detail) VALUES(?,?,?)""",
        (attempt_id, kind, detail[:100]))


def _ensure_not_stopped(store):
    with store._connect() as con:
        if stopped(con):
            raise PermissionError("비상정지 중 고객지원 SMTP 발송 차단")


def send(store, case_id, host, port, sender, recipient, username,
         password, owner_note, confirmation_prefix):
    """명시적 관리자 클릭 후 고객지원 답변 원문 1회 전송, 자동 재시도 없음."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if type(port) is not int or port != 465:
        raise PermissionError("인증서 검증 SMTP_SSL 465 포트만 허용")
    host = _host(host)
    sender = _email(sender)
    recipient = _email(recipient)
    if (type(username) is not str or not 1 <= len(username) <= 254
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in username)):
        raise ValueError("SMTP 계정 형식 오류")
    if type(password) is not str or not password or len(password) > 4096:
        raise PermissionError("일회성 SMTP 비밀번호가 필요합니다")
    if (type(owner_note) is not str
            or not 5 <= len(owner_note.strip()) <= 200
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in owner_note)):
        raise ValueError("관리자 발송 사유 5~200자/제어문자 금지")
    case, body = _approved_reply(store, case_id)
    if (type(confirmation_prefix) is not str
            or confirmation_prefix != case["reply_sha256"][:12]):
        raise PermissionError("미리보기에서 확인한 승인 답변 SHA256 앞 12자리가 다릅니다")
    message_id = make_msgid(idstring=uuid4().hex,
                            domain=sender.split("@", 1)[1])
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 실제 고객지원 발송 금지")
        if con.execute("""SELECT 1 FROM aiwack_customer_reply_smtp_attempts
            WHERE case_id=?""", (case_id,)).fetchone():
            raise PermissionError("이 문의의 이전 SMTP 시도가 있어 재전송 금지")
        row = con.execute("""SELECT state,task_id,artifact_id,reply_sha256
            FROM aiwack_customer_cases WHERE id=?""", (case_id,)).fetchone()
        if (not row or row[0] not in ("response_ready", "closed")
                or int(row[1]) != case["task_id"]
                or row[2] != case["artifact_id"]
                or row[3] != case["reply_sha256"]
                or cases._reply_proof(con, int(row[1]), int(row[2])) != row[3]
                or not cases._chief_call_audited(con, int(row[2]))):
            raise PermissionError("발송 직전 고객지원 승인 원본 변경")
        attempt_id = int(con.execute("""INSERT INTO
            aiwack_customer_reply_smtp_attempts(
              case_id,artifact_id,reply_sha256,sender,recipient,smtp_host,
              message_id,owner_note,status)
            VALUES(?,?,?,?,?,?,?,?,'claimed')""",
            (case_id,case["artifact_id"],case["reply_sha256"],sender,
             recipient,host,message_id,owner_note.strip())).lastrowid)
        _event(con, attempt_id, "owner_claimed", "관리자 실제 발송 승인")
    phase = "before_connection"
    state = "outcome_unknown"
    error_kind = ""
    try:
        latest, latest_body = _approved_reply(store, case_id)
        if latest["reply_sha256"] != case["reply_sha256"] or latest_body != body:
            raise PermissionError("발송 직전 승인 원문 변경")
        _ensure_not_stopped(store)
        message = EmailMessage()
        message["From"] = sender
        message["To"] = recipient
        message["Subject"] = "AIWACK 고객지원 답변 | " + case["case_ref"]
        message["Message-ID"] = message_id
        message.set_content(body)
        phase = "connection_started"
        with smtplib.SMTP_SSL(host, port, timeout=25,
                             context=ssl.create_default_context()) as smtp:
            phase = "authentication"
            smtp.login(username, password)
            _ensure_not_stopped(store)
            phase = "message_sending"
            refused = smtp.send_message(message, from_addr=sender,
                                        to_addrs=[recipient])
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
            phase = "smtp_accepted"
        state = "accepted_by_smtp"
    except (smtplib.SMTPException, OSError, ValueError,
            PermissionError) as exc:
        error_kind = type(exc).__name__[:70]
        state = ("not_sent" if phase in
                 ("before_connection", "connection_started", "authentication")
                 else "outcome_unknown")
        if phase == "smtp_accepted":
            state = "accepted_by_smtp"
    finally:
        with store._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("""UPDATE aiwack_customer_reply_smtp_attempts
                SET status=?,error_kind=?,finished_at=CURRENT_TIMESTAMP
                WHERE id=? AND status='claimed'""",
                (state,error_kind,attempt_id)).rowcount:
                _event(con,attempt_id,
                       "smtp_accepted" if state=="accepted_by_smtp" else state,
                       error_kind)
    return {
        "attempt_id": attempt_id, "case_id": case_id, "status": state,
        "smtp_server_accepted": state == "accepted_by_smtp",
        "recipient": recipient, "message_id": message_id,
        "error_kind": error_kind, "automatic_retry": False,
        "actual_customer_inbox_receipt_verified": False,
        "actual_gguf_binary_independently_verified": False,
        "external_payment_or_refund_performed": False
    }


def history(store, limit=50):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("고객지원 SMTP 감사 조회 1~100건")
    with store._connect() as con:
        initialize(con)
        rows = con.execute("""SELECT id,case_id,artifact_id,reply_sha256,
            sender,recipient,smtp_host,message_id,status,error_kind,
            claimed_at,finished_at
            FROM aiwack_customer_reply_smtp_attempts
            ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
    keys = ("id","case_id","artifact_id","reply_sha256","sender",
            "recipient","smtp_host","message_id","status","error_kind",
            "claimed_at","finished_at")
    return [dict(zip(keys,row)) for row in rows]
