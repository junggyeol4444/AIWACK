"""실제 SQLite 운영·재무 근거를 총괄 GGUF 판단용으로 묶는 읽기 전용 원본.

금액은 은행/PG 독립 확정 매출이 아니며 모델의 주장은 사실로 승격되지 않는다.
외부 네트워크·결제·게시·고객 발송은 이 모듈에서 실행하지 않는다.
"""
from __future__ import annotations

import hashlib
import json


def canonical(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), default=str)
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def snapshot(store, domain):
    store.require_permission("company:manage")
    if domain == "operations":
        from desktop import company_operational_incidents as incidents
        from desktop import company_department_workload as workload
        records = incidents.history(store, limit=20)
        state = workload.snapshot(store)
        data = {
            "domain": domain,
            "incident_rows": [{
                "id": x["id"], "kind": x["kind"],
                "source_id": x["source_id"], "decision": x["decision"],
                "current_source_state": x["current_source_state"],
                "evidence_sha256": x["evidence_sha256"],
            } for x in records],
            "departments": state["departments"],
            "workload_sha256": state["snapshot_sha256"],
            "process_liveness_verified": False,
        }
        has_evidence = bool(records or state["departments"])
    elif domain == "commerce":
        from desktop import company_order_exception_queue as exceptions
        from desktop import company_local_order_finance as finance
        record = finance.snapshot(store, limit=30)
        cases = exceptions.history(store, limit=20)
        data = {
            "domain": domain,
            "orders": record["orders"],
            "inspected_orders": record["inspected_orders"],
            "local_signed_settlement_evidence_minor":
                record["local_signed_settlement_evidence_minor"],
            "local_accepted_refund_evidence_minor":
                record["local_accepted_refund_evidence_minor"],
            "unlinked_refund_event_count": record["unlinked_refund_event_count"],
            "pending_cancel_request_count": record["pending_cancel_request_count"],
            "exceptions": [{
                "id": x.get("id"), "order_id": x.get("order_id"),
                "kind": x.get("kind"), "source_sha256": x.get("source_sha256"),
            } for x in cases],
            "actual_revenue_minor": None,
            "actual_profit_minor": None,
            "independent_pg_or_bank_verified": False,
            "actual_customer_delivery_sent": False,
        }
        has_evidence = bool(record["inspected_orders"] or cases)
    else:
        raise ValueError("실제 총괄 분석 대상은 operations/commerce만 가능합니다.")
    raw, digest = canonical(data)
    return {"domain": domain, "evidence": data, "raw": raw,
            "sha256": digest, "has_evidence": has_evidence,
            "external_action_executed": False,
            "independent_external_verification": False}
