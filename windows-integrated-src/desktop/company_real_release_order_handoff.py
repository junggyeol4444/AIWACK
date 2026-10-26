"""Link a real GGUF-approved multi-file release to a real local order.

Owner-triggered preparation of a *local* delivery handoff manifest only.
The order's existing approved product-document artifact must be among the
release's actually approved employee/chief source artifacts. The order's
local packet, source model calls, accepted owner reviews and files are
rechecked before writing. Payment/bank CSV/HMAC are local evidence, not
independently verified transactions or proof of customer delivery.

Never sends messages, modifies customer accounts, runs generated source,
approves a refund, or rewrites the original paid-order evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from desktop import company_local_order_fulfillment as orders
from desktop import company_local_delivery_packets as packets
from desktop import company_actual_release_bundles as releases
from desktop.stage87_90_management import stopped

MAX_MANIFEST=16384
_NAME=re.compile(r"order_approved_model_handoff_[0-9a-f]{32}\.json\Z")


def _canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,
                      separators=(",",":"))


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _folder(store):
    return Path(store.path).resolve().parent / "aiwack_local_model_order_handoffs"


def initialize(con):
    orders.initialize(con)
    packets.initialize(con)
    releases.initialize(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_real_release_order_handoffs(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      order_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_local_order_intakes(id),
      release_id INTEGER NOT NULL REFERENCES aiwack_actual_model_releases(id),
      packet_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_local_order_delivery_packets(id),
      product_document_id INTEGER NOT NULL REFERENCES aiwack_approved_product_documents(id),
      product_artifact_id INTEGER NOT NULL REFERENCES company_task_artifacts(id),
      release_sha256 TEXT NOT NULL CHECK(length(release_sha256)=64),
      product_document_sha256 TEXT NOT NULL CHECK(length(product_document_sha256)=64),
      local_packet_sha256 TEXT NOT NULL CHECK(length(local_packet_sha256)=64),
      manifest_sha256 TEXT NOT NULL CHECK(length(manifest_sha256)=64),
      manifest_filename TEXT NOT NULL UNIQUE,
      owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    for action in ("UPDATE","DELETE"):
        con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_release_order_handoff_no_%s
          BEFORE %s ON aiwack_real_release_order_handoffs
          BEGIN SELECT RAISE(ABORT,'실제 AI 상품 주문 준비 원본 불변'); END"""
          %(action.lower(),action))


def _source(con,order_id,release_id,packet_id):
    order=orders._verify(con,order_id)
    if not order["approved"] or order["cancel_requested"] or \
       order["accepted_refund_minor"] or order["unlinked_refund_ids"]:
        raise PermissionError("로컬 포장 승인·미취소·미환불 주문만 다중 상품 준비 가능")
    record=con.execute("""SELECT id,product_document_id,source_sha256,
       packet_sha256 FROM aiwack_local_order_delivery_packets
       WHERE id=? AND order_id=?""",(packet_id,order_id)).fetchone()
    if not record or record[1]!=order["product_document_id"] or \
       record[2]!=order["document_sha256"] or record[3]!=order["document_sha256"]:
        raise ValueError("주문과 로컬 준비 파일의 실제 원본 SHA256 불일치")
    doc=con.execute("""SELECT artifact_id,file_sha256,artifact_sha256,catalog_item_id
       FROM aiwack_approved_product_documents WHERE id=?""",
       (order["product_document_id"],)).fetchone()
    if not doc or doc[1]!=order["document_sha256"] or \
       doc[3]!=order["catalog_item_id"]:
        raise ValueError("해당 주문의 승인된 상품 문서 원본 확인 실패")
    product_artifact_id=int(doc[0])
    release=con.execute("""SELECT bundle_sha256,manifest_json,manifest_sha256
        FROM aiwack_actual_model_releases WHERE id=?""",(release_id,)).fetchone()
    if not release:
        raise ValueError("실제 직원/총괄 모델 승인 다중 상품 묶음 없음")
    release_sha,manifest_json,manifest_sha=release
    if _sha(manifest_json.encode("utf-8"))!=manifest_sha:
        raise ValueError("다중 직원 AI 묶음 매니페스트 변경")
    items=con.execute("""SELECT artifact_id,kind,source_sha256,
       employee_call_id,chief_report_id,chief_call_id
       FROM aiwack_actual_model_release_items
       WHERE release_id=? ORDER BY ordinal""",(release_id,)).fetchall()
    if not 2<=len(items)<=20 or product_artifact_id not in [r[0] for r in items]:
        raise ValueError("주문 승인 문서의 실제 직원 결과물이 ZIP 묶음에 포함돼야 합니다")
    # Verify every item's currently authorized model output and approvals.
    from desktop.company_actual_release_bundles import _proofs, _manifest
    candidates=_proofs(con,[(int(row[0]),str(row[1])) for row in items])
    if _manifest(json.loads(manifest_json)["title"],candidates)!=json.loads(manifest_json):
        raise ValueError("실제 GGUF 다중 승인 소스 감사 원본이 바뀌었습니다")
    if any((row[2]!=candidate["source_sha256"] or
            row[3]!=candidate["employee_call_id"] or
            row[4]!=candidate["chief_report_id"] or
            row[5]!=candidate["chief_call_id"])
           for row,candidate in zip(items,candidates)):
        raise PermissionError("제품 ZIP의 모델 호출·검수 원본 감사 불일치")
    if not any(row[0]==product_artifact_id and row[2]==doc[2]
               for row in items):
        raise PermissionError("주문·실제 직원 결과 원본 SHA256 연결이 아닙니다")
    return {
        "order_id":int(order_id),"release_id":int(release_id),
        "local_packet_id":int(packet_id),
        "product_document_id":int(order["product_document_id"]),
        "product_artifact_id":product_artifact_id,
        "release_sha256":release_sha,
        "product_document_sha256":order["document_sha256"],
        "local_packet_sha256":record[3],
        "release_artifacts":[int(item[0]) for item in items],
        "actual_order_provider_independent_verified":False,
        "independent_bank_verification":False,
        "delivered_to_customer":False,
        "external_payment_executed":False,
    }


def _manifest(proof):
    # Do not put customer personal data or financial amount in deliverable.
    return {**proof,
        "kind":"AIWACK_owner_prepared_local_delivery_manifest_v1",
        "file_created_from_original_owner_approved_GGUF_output":True,
        "owner_final_delivery_review_required":True,
        "external_service_upload_performed":False,
        "real_revenue_confirmed":False}


def create(store,order_id,release_id,packet_id,note):
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    for n,v in (("주문",order_id),("승인 다중 제품",release_id),("준비 파일",packet_id)):
        if type(v) is not int or v<1:raise ValueError(n+" 번호 오류")
    if type(note) is not str or not 5<=len(note.strip())<=200:
        raise ValueError("관리자 주문별 상품 준비 사유는 5~200자여야 합니다")
    # Verify filesystem files first, then the SQLite source again under
    # BEGIN IMMEDIATE to reject concurrent cancellation or changed artifacts.
    p=packets.read(store,packet_id)
    r=releases.read(store,release_id)
    o=orders.read(store,order_id)
    if p["order_id"]!=order_id or o["local_cancel_requested"]:
        raise PermissionError("주문·로컬 준비 파일 불일치 또는 취소 요청")
    if r["id"]!=release_id:
        raise ValueError("실제 승인 AI 제품 묶음 원본 불일치")
    root=_folder(store)
    if root.is_symlink():raise ValueError("고객 전달 준비 폴더 링크 금지")
    filename="order_approved_model_handoff_"+uuid4().hex+".json"
    file=root/filename
    wrote=committed=False
    try:
        with store._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            initialize(con)
            if stopped(con):raise PermissionError("비상정지 중 주문별 상품 준비 차단")
            if con.execute("""SELECT 1 FROM aiwack_real_release_order_handoffs
               WHERE order_id=?""",(order_id,)).fetchone():
                raise ValueError("이미 주문별 다중 AI 제품 준비 원본이 있습니다")
            proof=_source(con,order_id,release_id,packet_id)
            if (p["packet_sha256"]!=proof["local_packet_sha256"] or
                    r["sha256"]!=proof["release_sha256"]):
                raise ValueError("제품 파일·상품 준비 원본이 준비 중에 변경")
            raw=(_canonical(_manifest(proof))+"\n").encode("utf-8")
            if not 1<=len(raw)<=MAX_MANIFEST:
                raise ValueError("승인된 주문별 전달 매니페스트 16KiB 초과")
            root.mkdir(parents=True,exist_ok=True)
            if root.is_symlink():raise ValueError("주문 패키지 폴더 심볼릭 링크 금지")
            with file.open("xb") as stream:
                wrote=True
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            handoff_id=int(con.execute("""INSERT INTO aiwack_real_release_order_handoffs(
              order_id,release_id,packet_id,product_document_id,
              product_artifact_id,release_sha256,product_document_sha256,
              local_packet_sha256,manifest_sha256,manifest_filename,owner_note)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
              (order_id,release_id,packet_id,proof["product_document_id"],
               proof["product_artifact_id"],proof["release_sha256"],
               proof["product_document_sha256"],proof["local_packet_sha256"],
               _sha(raw),filename,note.strip())).lastrowid)
        committed=True
        return read(store,handoff_id)
    except BaseException:
        if wrote and not committed:
            file.unlink(missing_ok=True)
        raise


def read(store,handoff_id):
    store.require_permission("company:manage")
    if type(handoff_id) is not int or handoff_id<1:
        raise ValueError("주문별 GGUF 묶음 준비 번호 오류")
    with store._connect() as con:
        initialize(con)
        row=con.execute("""SELECT order_id,release_id,packet_id,
          product_document_id,product_artifact_id,release_sha256,
          product_document_sha256,local_packet_sha256,
          manifest_sha256,manifest_filename,created_at
          FROM aiwack_real_release_order_handoffs WHERE id=?""",
          (handoff_id,)).fetchone()
        if not row:raise ValueError("로컬 상품 묶음 연결 원본 없음")
        (order_id,release_id,packet_id,doc_id,artifact_id,release_sha,
         doc_sha,packet_sha,manifest_sha,filename,created)=row
        # On later customer cancellation this original handoff still exists,
        # and its historic source evidence must not be rewritten/hidden.
        release_row=con.execute("""SELECT bundle_sha256 FROM
            aiwack_actual_model_releases WHERE id=?""",(release_id,)).fetchone()
        if not release_row or release_row[0]!=release_sha:
            raise ValueError("다중 GGUF 제품 원본 사라짐/변경")
        original_doc=con.execute("""SELECT artifact_id,file_sha256 FROM
            aiwack_approved_product_documents WHERE id=?""",(doc_id,)).fetchone()
        if original_doc!=(artifact_id,doc_sha):
            raise ValueError("승인된 주문 상품 문서 원본 변경")
        local_packet=con.execute("""SELECT order_id,source_sha256,packet_sha256
            FROM aiwack_local_order_delivery_packets WHERE id=?""",
            (packet_id,)).fetchone()
        if local_packet!=(order_id,packet_sha,packet_sha):
            raise ValueError("주문에 연결한 실제 로컬 상품 준비 원본 변경")
    release=releases.read(store,int(release_id))
    packet=packets.read(store,int(packet_id))
    if release["sha256"]!=release_sha or packet["packet_sha256"]!=packet_sha:
        raise ValueError("실제 파일/주문 관련 SHA256 불일치")
    if not isinstance(filename,str) or not _NAME.fullmatch(filename):
        raise ValueError("고객 전달 준비 파일명 원본 불일치")
    path=_folder(store)/filename
    if _folder(store).is_symlink() or path.is_symlink() or not path.is_file():
        raise ValueError("주문별 모델 전달 준비 파일 누락")
    raw=path.read_bytes()
    if len(raw)>MAX_MANIFEST or _sha(raw)!=manifest_sha:
        raise ValueError("주문별 제품 준비 JSON 원본 SHA256 훼손")
    manifest=json.loads(raw)
    if (manifest.get("order_id")!=order_id or
        manifest.get("release_id")!=release_id or
        manifest.get("local_packet_id")!=packet_id or
        manifest.get("product_artifact_id")!=artifact_id or
        manifest.get("release_sha256")!=release_sha or
        manifest.get("product_document_sha256")!=doc_sha or
        manifest.get("local_packet_sha256")!=packet_sha or
        manifest.get("delivered_to_customer") is not False):
        raise ValueError("실제 승인된 모델 주문 준비 매니페스트 원본 변경")
    current=orders.read(store,int(order_id))
    return {"id":handoff_id,"order_id":int(order_id),"release_id":int(release_id),
            "packet_id":int(packet_id),"prepared_manifest_path":str(path),
            "manifest_sha256":manifest_sha,"release_sha256":release_sha,
            "source_artifact_id":int(artifact_id),"created_at":created,
            "current_cancel_requested":current["local_cancel_requested"],
            "current_refund_evidence_minor":current["accepted_refund_minor"],
            "current_owner_delivery_ready":bool(
                current["local_package_approved"] and
                not current["local_cancel_requested"] and
                not current["accepted_refund_minor"] and
                not current["unlinked_refund_ids"]),
            "actual_customer_sent":False,"actual_revenue_confirmed":False,
            "independent_bank_or_pg_verified":False,
            "model_or_external_service_reexecuted":False}


def history(store,limit=40):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("주문별 제품 준비 이력 1~100건")
    with store._connect() as con:
        initialize(con)
        ids=[int(row[0]) for row in con.execute("""SELECT id FROM
            aiwack_real_release_order_handoffs
            ORDER BY id DESC LIMIT ?""",(limit,)).fetchall()]
    return [read(store,i) for i in ids]
