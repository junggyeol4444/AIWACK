"""서명 거래·관리자 결정·소유자 선택 은행 CSV 대사 현황.
로컬 증빙일 뿐 실제 PG/은행 확인 또는 확정 매출이 아니다. 외부 호출 없음.
"""
from __future__ import annotations
from desktop import company_bank_reconciliation as bank

def snapshot(store, business_id=None, limit=100):
    store.require_permission("company:manage")
    if business_id is not None and (type(business_id) is not int or business_id < 1):
        raise ValueError("사업 번호는 양의 정수여야 합니다.")
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("재무 증빙 조회 범위는 1~500건입니다.")
    with store._connect() as con:
        bank.initialize(con)
        sql = """SELECT p.id,p.business_id,p.provider,p.transaction_id,
                  p.event_type,p.amount_minor,p.event_sha256,p.owner_decision,
                  m.id,m.bank_reference,m.event_sha256,m.amount_minor,
                  b.source_sha256
                  FROM aiwack_provider_payment_events p
                  LEFT JOIN aiwack_bank_reconciliation_matches m
                    ON m.payment_event_id=p.id
                  LEFT JOIN aiwack_bank_reconciliation_batches b ON b.id=m.batch_id"""
        args = []
        if business_id is not None:
            sql += " WHERE p.business_id=?"
            args.append(business_id)
        sql += " ORDER BY p.id DESC LIMIT ?"
        args.append(limit)
        rows = con.execute(sql, args).fetchall()
        totals = {kind: {"accepted_events": 0, "signed_amount_minor": 0,
                         "bank_csv_matched_events": 0, "bank_csv_matched_minor": 0}
                  for kind in ("settlement", "refund", "expense")}
        details = []
        for (eid,bid,provider,tx,kind,amount,digest,decision,match_id,
             reference,match_digest,match_amount,source_sha) in rows:
            intact = (match_id is None or
                      (digest == match_digest and amount == match_amount
                       and source_sha is not None))
            if not intact:
                raise ValueError("은행 CSV 대사 원본과 거래 서명 기록이 일치하지 않습니다.")
            matched = match_id is not None and decision == "accepted"
            if decision == "accepted":
                totals[kind]["accepted_events"] += 1
                totals[kind]["signed_amount_minor"] += int(amount)
                if matched:
                    totals[kind]["bank_csv_matched_events"] += 1
                    totals[kind]["bank_csv_matched_minor"] += int(amount)
            details.append({"event_id":int(eid),"business_id":int(bid),
                            "provider":provider,"transaction_id":tx,
                            "kind":kind,"amount_minor":int(amount),
                            "owner_decision":decision,
                            "bank_csv_match_id":match_id if matched else None,
                            "bank_reference":reference if matched else None,
                            "evidence_integrity_checked":intact,
                            "independently_verified":False})
    return {"business_id":business_id,"events_in_page":len(details),
            "page_limited":len(details)==limit,"totals_for_page_only":totals,
            "events":details,"currency":"KRW",
            "real_revenue_confirmed":False,
            "independent_bank_or_pg_verified":False,
            "actual_payment_or_refund_executed":False,"external_network_used":False}
