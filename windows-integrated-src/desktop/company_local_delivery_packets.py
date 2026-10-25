"""관리자 승인된 실제 상품 문서를 주문별 로컬 전달 준비 파일로 보존한다.

고객 전송, 외부 배송, 실제 결제 확인을 수행하지 않는다.
로컬 준비 파일은 이미 검수된 직원 결과물의 원문 바이트를 복사한다.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from desktop import company_local_order_fulfillment as orders
from desktop import company_product_documents as documents
from desktop.stage87_90_management import stopped


def _digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def initialize(con):
    orders.initialize(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_local_order_delivery_packets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_local_order_intakes(id),
        product_document_id INTEGER NOT NULL REFERENCES aiwack_approved_product_documents(id),
        source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64),
        filename TEXT NOT NULL UNIQUE,
        packet_sha256 TEXT NOT NULL CHECK(length(packet_sha256)=64),
        byte_count INTEGER NOT NULL CHECK(byte_count BETWEEN 1 AND 32768),
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        receipt_sha256 TEXT NOT NULL CHECK(length(receipt_sha256)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    for action in ('UPDATE', 'DELETE'):
        con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_delivery_packet_no_"""
                    + action.lower() + """ BEFORE """ + action
                    + """ ON aiwack_local_order_delivery_packets BEGIN
                        SELECT RAISE(ABORT,'상품 준비 원본 이력 변경 금지'); END""")


def _folder(store):
    return Path(store.path).resolve().parent / 'aiwack_local_delivery_packets'


def _payload(order_id, document_id, digest, filename, size, note):
    return dict(order_id=order_id, product_document_id=document_id,
                source_sha256=digest, filename=filename,
                packet_sha256=digest, byte_count=size, owner_note=note)


def prepare(store, order_id: int, owner_note: str) -> dict:
    """소유자 별도 확인 후 1주문당 1회만 실제 로컬 파일을 준비."""
    store.require_permission('company:manage')
    orders._id(order_id, '주문')
    note = orders._text(owner_note, '관리자 상품 준비 사유', 200)
    if len(note) < 5:
        raise ValueError('관리자 사유는 5자 이상이어야 합니다.')
    order = orders.read(store, order_id)
    if (not order['local_package_approved'] or order['local_cancel_requested']
            or order['accepted_refund_minor'] or order['unlinked_refund_ids']):
        raise ValueError('승인·미취소·미환불 주문만 로컬 준비할 수 있습니다.')
    document = documents.read(store, int(order['product_document_id']))
    source_path = Path(document['path'])
    if source_path.is_symlink() or not source_path.is_file():
        raise ValueError('승인 문서 경로가 실제 일반 파일이 아닙니다.')
    raw = source_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if (not raw or len(raw) > documents.MAX_DOCUMENT_BYTES
            or digest != document['sha256']
            or digest != order['document_sha256']
            or len(raw) != document['byte_count']):
        raise ValueError('원본 승인 상품 문서 SHA256 또는 크기 불일치')
    folder = _folder(store)
    if folder.is_symlink():
        raise ValueError('로컬 상품 준비 폴더 링크 금지')
    filename = 'order_' + uuid4().hex + '.md'
    target = folder / filename
    wrote = committed = False
    try:
        with store._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            initialize(con)
            if stopped(con):
                raise PermissionError('비상정지 중 상품 준비 금지')
            fresh = orders._verify(con, order_id)
            if (not fresh['approved'] or fresh['cancel_requested']
                    or fresh['accepted_refund_minor'] or fresh['unlinked_refund_ids']
                    or fresh['product_document_id'] != document['id']
                    or fresh['document_sha256'] != digest):
                raise ValueError('상품 준비 중 주문·환불·상품 원본 상태 변경')
            if con.execute('SELECT 1 FROM aiwack_local_order_delivery_packets WHERE order_id=?',
                           (order_id,)).fetchone():
                raise ValueError('이미 상품 준비 파일이 존재합니다. 중복 준비 금지')
            folder.mkdir(parents=True, exist_ok=True)
            if folder.is_symlink():
                raise ValueError('로컬 준비 폴더 링크 금지')
            with target.open('xb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            wrote = True
            values = _payload(order_id, document['id'], digest, filename, len(raw), note)
            receipt = _digest(values)
            packet_id = int(con.execute("""INSERT INTO aiwack_local_order_delivery_packets
                (order_id,product_document_id,source_sha256,filename,packet_sha256,
                 byte_count,owner_note,receipt_sha256)
                VALUES (?,?,?,?,?,?,?,?)""",
                (order_id, document['id'], digest, filename, digest,
                 len(raw), note, receipt)).lastrowid)
        committed = True
        return read(store, packet_id)
    except BaseException:
        if wrote and not committed:
            target.unlink(missing_ok=True)
        raise


def read(store, packet_id: int) -> dict:
    store.require_permission('company:manage')
    orders._id(packet_id, '상품 준비')
    with store._connect() as con:
        initialize(con)
        row = con.execute("""SELECT order_id,product_document_id,source_sha256,
              filename,packet_sha256,byte_count,owner_note,receipt_sha256
              FROM aiwack_local_order_delivery_packets WHERE id=?""",
              (packet_id,)).fetchone()
        if not row:
            raise ValueError('해당 로컬 상품 준비 기록이 없습니다.')
    order_id, doc_id, source_sha, filename, packet_sha, count, note, receipt = row
    values = _payload(order_id, doc_id, source_sha, filename, count, note)
    if (receipt != _digest(values) or source_sha != packet_sha
            or not isinstance(filename, str) or len(filename) != 41
            or not filename.startswith('order_') or not filename.endswith('.md')
            or any(ch not in '0123456789abcdef' for ch in filename[6:-3])):
        raise ValueError('상품 준비 감사 영수증 무결성 오류')
    order = orders.read(store, int(order_id))
    document = documents.read(store, int(doc_id))
    if (order['product_document_id'] != doc_id or
            order['document_sha256'] != source_sha or
            document['sha256'] != source_sha):
        raise ValueError('주문·원본 상품 파일과 준비 기록 불일치')
    folder = _folder(store)
    target = folder / filename
    if folder.is_symlink() or target.is_symlink() or not target.is_file():
        raise ValueError('로컬 상품 준비 파일이 없거나 링크입니다.')
    raw = target.read_bytes()
    if (len(raw) != count or len(raw) > documents.MAX_DOCUMENT_BYTES
            or hashlib.sha256(raw).hexdigest() != packet_sha
            or raw != Path(document['path']).read_bytes()):
        raise ValueError('로컬 준비 파일과 실제 승인 문서 바이트 불일치')
    return dict(id=packet_id, order_id=order_id, product_document_id=doc_id,
                local_packet_path=str(target), packet_sha256=packet_sha,
                byte_count=count, owner_note=note, receipt_sha256=receipt,
                actual_customer_delivery_sent=False, actual_revenue_confirmed=False,
                independent_pg_or_bank_verified=False)


def list_packets(store, limit: int = 50) -> list[dict]:
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('상품 준비 조회 범위는 1~200건')
    with store._connect() as con:
        initialize(con)
        ids = [int(row[0]) for row in con.execute(
            'SELECT id FROM aiwack_local_order_delivery_packets ORDER BY id DESC LIMIT ?',
            (limit,)).fetchall()]
    return [read(store, packet_id) for packet_id in ids]
