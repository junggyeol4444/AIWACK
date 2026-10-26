"""Owner-selected ISO 20022 camt.053 bank statement XML -> existing local bank reconciliation.

This is not a bank API connector or independent proof that the supplied file
originated from the bank. It accepts the actual file BYTES chosen by the owner,
reads one explicit transaction reference per entry, and atomically joins it
to the existing authenticated + separately owner-approved provider event.
No external HTTP, bank login, transfer, refund, or payment is performed.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from desktop import company_bank_reconciliation as bank
from desktop import company_payment_reconciliation as provider
from desktop.stage87_90_management import stopped

MAX_BYTES=4*1024*1024
MAX_ENTRIES=2000
SCALE_LIMIT=10**12
CURRENCY="KRW"


def _local(tag):
    return tag.rsplit("}",1)[-1]


def _children(node,name):
    return [c for c in node if _local(c.tag)==name]


def _one(node,name):
    matches=_children(node,name)
    if len(matches)!=1:
        raise ValueError("은행 camt.053 XML의 "+name+" 항목이 누락되거나 중복되었습니다.")
    return matches[0]


def _text(node,name):
    element=_one(node,name)
    if len(element):
        raise ValueError("은행 거래 "+name+" 값이 단순 텍스트가 아닙니다.")
    raw=element.text or ""
    value=raw.strip()
    if not value or len(value)>200:
        raise ValueError("은행 거래 "+name+" 값 누락/길이 초과")
    return value


def _amount(n):
    value=(n.text or "").strip()
    if n.get("Ccy")!=CURRENCY:
        raise ValueError("은행 원문 통화가 KRW가 아닙니다.")
    if not re.fullmatch(r"[0-9]{1,13}(?:\.[0-9]{1,2})?",value):
        raise ValueError("KRW 은행 금액 형식 오류")
    try:
        money=Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("은행 금액 해석 실패") from exc
    if money!=money.to_integral_value() or not 0<money<=SCALE_LIMIT:
        raise ValueError("KRW 은행 거래 금액은 양의 정수 원화여야 합니다.")
    return int(money)


def _read_statement(path):
    if not isinstance(path,(str,Path)):
        raise ValueError("사용자가 선택한 은행 camt 파일 경로가 필요합니다.")
    p=Path(path)
    if p.suffix.lower() not in (".xml",".camt") or p.is_symlink() or not p.is_file():
        raise ValueError("일반 로컬 camt.053 XML 파일만 가져올 수 있습니다.")
    if not 1<=p.stat().st_size<=MAX_BYTES:
        raise ValueError("은행 camt XML 용량 1~4MiB 제한")
    raw=p.read_bytes()
    if (not raw or len(raw)>MAX_BYTES or b"\x00" in raw or
            re.search(br"<!\s*(DOCTYPE|ENTITY)\b",raw,re.I)):
        raise ValueError("은행 XML의 DTD/외부 엔터티/바이너리 입력 거부")
    try:
        root=ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("은행 ISO20022 camt.053 XML 파싱 실패") from exc
    if _local(root.tag)!="Document" or len(root)!=1:
        raise ValueError("ISO20022 camt.053 Document 루트 오류")
    document=_one(root,"BkToCstmrStmt")
    statements=_children(document,"Stmt")
    if not 1<=len(statements)<=MAX_ENTRIES:
        raise ValueError("은행 camt.053 Stmt 항목 개수 오류")
    transactions=[]
    unique_refs=set()
    for statement in statements:
        # Require an actual bank statement identifier but avoid storing it.
        _text(statement,"Id")
        entries=_children(statement,"Ntry")
        for entry in entries:
            if len(transactions)>=MAX_ENTRIES:
                raise ValueError("은행 camt.053 거래 최대 2000건")
            reference=_text(entry,"NtryRef")
            if not provider.KEY.fullmatch(reference) or reference in unique_refs:
                raise ValueError("은행 camt.053 NtryRef 누락/중복/형식 오류")
            unique_refs.add(reference)
            money=_amount(_one(entry,"Amt"))
            flow=_text(entry,"CdtDbtInd")
            if flow not in ("CRDT","DBIT"):
                raise ValueError("은행 camt.053 입금/출금 상태 오류")
            status_element=_one(entry,"Sts")
            status=(_text(status_element,"Cd") if _children(status_element,"Cd")
                    else _text(entry,"Sts"))
            if status not in ("BOOK","BOOKED"):
                raise ValueError("미확정 은행 거래는 대사할 수 없습니다.")
            details=_one(entry,"NtryDtls")
            txs=_children(details,"TxDtls")
            if len(txs)!=1:
                raise ValueError("각 은행 거래당 명확한 TxDtls 1건만 지원")
            refs=_one(txs[0],"Refs")
            # Require the bank's structured transaction ID, not user-controlled
            # free-text remittance or a guessed provider identifier.
            transaction=_text(refs,"TxId")
            if not provider.KEY.fullmatch(transaction):
                raise ValueError("은행 거래 정규 TxId 형식 오류")
            row=f"{reference}\x1f{transaction}\x1f{flow}\x1f{money}\x1fKRW"
            transactions.append({
                "bank_reference":reference,"transaction_id":transaction,
                "direction":flow,"amount_minor":money,
                "row_sha256":hashlib.sha256(row.encode("utf-8")).hexdigest()
            })
    if not transactions:
        raise ValueError("확정된 은행 Ntry 거래가 없습니다.")
    return hashlib.sha256(raw).hexdigest(),len(raw),transactions


def initialize(con):
    bank.initialize(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_camt_bank_sources(
        batch_id INTEGER PRIMARY KEY REFERENCES aiwack_bank_reconciliation_batches(id),
        source_kind TEXT NOT NULL CHECK(source_kind='ISO20022_camt053'),
        provider TEXT NOT NULL,
        business_id INTEGER NOT NULL REFERENCES managed_businesses(id),
        source_sha256 TEXT NOT NULL UNIQUE CHECK(length(source_sha256)=64),
        confirmed_xml_entries INTEGER NOT NULL CHECK(confirmed_xml_entries BETWEEN 1 AND 2000),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    for action in ("UPDATE","DELETE"):
        con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_camt_bank_sources_no_%s
           BEFORE %s ON aiwack_camt_bank_sources
           BEGIN SELECT RAISE(ABORT,'은행 camt 원본 기록 변경·삭제 금지'); END"""
           %(action.lower(),action))


def _match(con,entries,provider_name,business_id):
    matched=[]
    seen_ids=set()
    for item in entries:
        flow=item["direction"]
        choices=con.execute("""SELECT id,event_sha256,event_type,amount_minor,
                 owner_decision,authenticated,currency
            FROM aiwack_provider_payment_events
            WHERE provider=? AND business_id=? AND transaction_id=?
              AND amount_minor=? AND currency='KRW'
              AND owner_decision='accepted' AND authenticated=1""",
              (provider_name,business_id,item["transaction_id"],
               item["amount_minor"])).fetchall()
        choices=[r for r in choices if
            (flow=="CRDT" and r[2]=="settlement") or
            (flow=="DBIT" and r[2] in ("refund","expense"))]
        if len(choices)!=1:
            raise ValueError("은행 TxId/금액/입출금과 승인된 공급자 거래 1건이 정확히 일치하지 않습니다: "
                             +item["bank_reference"][:30])
        rid,digest,kind,amount,decision,authenticated,currency=choices[0]
        if rid in seen_ids:
            raise ValueError("은행 camt 원본에서 공급자 거래 중복 참조")
        seen_ids.add(rid)
        if con.execute("""SELECT 1 FROM aiwack_bank_reconciliation_matches
           WHERE payment_event_id=? OR bank_reference=?""",
           (rid,item["bank_reference"])).fetchone():
            raise PermissionError("기존 은행 CSV/camt 대사와 동일한 참조/공급자 거래 중복")
        matched.append((item["bank_reference"],rid,digest,amount,item["row_sha256"]))
    return matched


def preview(store,file_path,provider_name,business_id):
    store.require_permission("company:manage")
    if not isinstance(provider_name,str) or not provider.KEY.fullmatch(provider_name):
        raise ValueError("기존 거래 공급자 이름 형식 오류")
    if type(business_id) is not int or business_id<1:
        raise ValueError("기존 회사 사업 번호 오류")
    sha,size,entries=_read_statement(file_path)
    with store._connect() as con:
        initialize(con)
        matches=_match(con,entries,provider_name,business_id)
    return {"source_sha256":sha,"source_bytes":size,"entry_count":len(entries),
            "matching_original_provider_events":len(matches),
            "provider":provider_name,"business_id":business_id,"currency":"KRW",
            "source_type":"owner_selected_ISO20022_camt053_XML",
            "verified_direct_bank_api":False,"verified_bank_issuer_signature":False,
            "verified_external_money_transfer":False,
            "no_existing_database_changes":True}


def import_owner_camt(store,file_path,provider_name,business_id):
    """Atomic strict reconciliation; a single mismatch rejects the whole XML."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if not isinstance(provider_name,str) or not provider.KEY.fullmatch(provider_name):
        raise ValueError("기존 거래 공급자 이름 형식 오류")
    if type(business_id) is not int or business_id<1:
        raise ValueError("기존 사업 번호 오류")
    sha,size,entries=_read_statement(file_path)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 은행 자료 대사 금지")
        if con.execute("""SELECT 1 FROM aiwack_bank_reconciliation_batches
            WHERE source_sha256=?""",(sha,)).fetchone():
            raise ValueError("이 은행 원본 파일은 이전에 이미 대사됐습니다.")
        if not con.execute("SELECT 1 FROM managed_businesses WHERE id=?",
                           (business_id,)).fetchone():
            raise ValueError("존재하지 않는 회사 사업 번호")
        matches=_match(con,entries,provider_name,business_id)
        batch=int(con.execute("""INSERT INTO aiwack_bank_reconciliation_batches
           (source_sha256,source_bytes,row_count) VALUES(?,?,?)""",
           (sha,size,len(matches))).lastrowid)
        for reference,event_id,digest,amount,row_digest in matches:
            con.execute("""INSERT INTO aiwack_bank_reconciliation_matches
               (batch_id,bank_reference,payment_event_id,event_sha256,
                amount_minor,row_sha256) VALUES(?,?,?,?,?,?)""",
                (batch,reference,event_id,digest,amount,row_digest))
        con.execute("""INSERT INTO aiwack_camt_bank_sources
            (batch_id,source_kind,provider,business_id,source_sha256,
             confirmed_xml_entries) VALUES(?,'ISO20022_camt053',?,?,?,?)""",
             (batch,provider_name,business_id,sha,len(entries)))
    return {"batch":bank.read(store,batch),
            "imported_camt_source":"owner_selected_XML_not_bank_API",
            "direct_bank_verified":False,
            "bank_issuer_signature_verified":False,
            "money_transferred_by_program":False}


def history(store,limit=30):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("camt 은행 감사 조회 1~100건")
    with store._connect() as con:
        initialize(con)
        rows=con.execute("""SELECT batch_id,provider,business_id,source_sha256,
            confirmed_xml_entries,created_at FROM aiwack_camt_bank_sources
            ORDER BY batch_id DESC LIMIT ?""",(limit,)).fetchall()
    result=[]
    for batch_id,provider_name,business_id,sha,count,created in rows:
        receipt=bank.read(store,int(batch_id))
        if receipt["source_sha256"]!=sha or receipt["matched_signed_events"]!=count:
            raise ValueError("기존 은행/공급자 원본 감사 연결 불일치")
        result.append({"bank_batch_id":int(batch_id),"provider":provider_name,
                       "business_id":int(business_id),"source_sha256":sha,
                       "count":int(count),"created_at":created,
                       "amount_minor":receipt["matched_amount_minor"],
                       "issuer_bank_independently_verified":False,
                       "real_bank_settlement_verified":False})
    return result
