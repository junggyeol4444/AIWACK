"""관리자 선택 은행 CSV와 승인된 서명 거래 증빙의 로컬 대사.

외부 은행 API 확인, 실제 입금 확인, PG 거래 실행을 하지 않는다.
CSV는 소유자가 가져온 미검증 자료이고 HMAC 이벤트 역시 공급자 독립 확인이 아니다.
"""
from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path
import re
import sqlite3

from desktop import company_payment_reconciliation as provider
from desktop.stage87_90_management import stopped

COLUMNS = ('bank_reference', 'provider', 'transaction_id', 'business_id',
           'event_type', 'amount_minor', 'currency')
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_ROWS = 2000
KEY = re.compile(r'[A-Za-z0-9._:-]{4,100}\Z')


def initialize(con: sqlite3.Connection) -> None:
    provider.initialize(con)
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_bank_reconciliation_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_sha256 TEXT NOT NULL UNIQUE CHECK(length(source_sha256)=64),
        source_bytes INTEGER NOT NULL CHECK(source_bytes BETWEEN 1 AND 4194304),
        row_count INTEGER NOT NULL CHECK(row_count BETWEEN 1 AND 2000),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_bank_reconciliation_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER NOT NULL REFERENCES aiwack_bank_reconciliation_batches(id),
        bank_reference TEXT NOT NULL UNIQUE,
        payment_event_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_provider_payment_events(id),
        event_sha256 TEXT NOT NULL CHECK(length(event_sha256)=64),
        amount_minor INTEGER NOT NULL CHECK(amount_minor>0),
        row_sha256 TEXT NOT NULL CHECK(length(row_sha256)=64))''')
    for table in ('aiwack_bank_reconciliation_batches','aiwack_bank_reconciliation_matches'):
        for action in ('UPDATE','DELETE'):
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()}
                BEFORE {action} ON {table} BEGIN
                SELECT RAISE(ABORT,'은행 CSV 대사 원본 기록은 변경·삭제할 수 없습니다'); END''')


def _load(path: Path):
    if not isinstance(path, Path):
        raise ValueError('은행 CSV는 선택한 로컬 파일이어야 합니다.')
    if path.suffix.lower() != '.csv' or path.is_symlink() or not path.is_file():
        raise ValueError('은행 CSV 파일 경로 또는 심볼릭 링크가 올바르지 않습니다.')
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError('은행 거래 원본 크기 제한(4MiB) 초과')
    raw = path.read_bytes()
    if not raw or len(raw)>MAX_SOURCE_BYTES or b'\x00' in raw:
        raise ValueError('은행 거래 파일 내용 오류')
    try:
        reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''),strict=True)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError('은행 CSV 열 이름·순서가 원본 요구 형식과 다릅니다.')
        parsed=[]
        seen=set()
        for row in reader:
            if len(parsed)>=MAX_ROWS:
                raise ValueError('은행 거래 파일 행수 제한(2000건) 초과')
            if None in row or any(value is None for value in row.values()):
                raise ValueError('은행 거래 CSV 열 개수 오류')
            row={key:value.strip() for key,value in row.items()}
            for key in ('bank_reference','provider','transaction_id'):
                if not KEY.fullmatch(row[key]):
                    raise ValueError('은행·공급자 거래 고유번호 형식 오류')
            reference=row['bank_reference']
            if reference in seen:
                raise ValueError('은행 거래 고유번호 중복')
            seen.add(reference)
            if row['event_type'] not in provider.VALID or row['currency']!='KRW':
                raise ValueError('은행 입출금 유형/원화 통화가 일치하지 않습니다.')
            if not re.fullmatch(r'[1-9][0-9]*', row['business_id']) or not re.fullmatch(r'[1-9][0-9]*',row['amount_minor']):
                raise ValueError('은행 거래 금액 또는 사업 ID가 정수가 아닙니다.')
            business=int(row['business_id']);amount=int(row['amount_minor'])
            if amount>10**12 or business>2**63-1:
                raise ValueError('은행 거래 금액·사업 ID 제한 초과')
            parsed.append((reference,row['provider'],row['transaction_id'],business,
                           row['event_type'],amount,hashlib.sha256(
                               ('\x1f'.join(row[key] for key in COLUMNS)).encode('utf-8')).hexdigest()))
    except (UnicodeError,csv.Error) as exc:
        raise ValueError('은행 CSV를 읽을 수 없습니다.') from exc
    if not parsed:
        raise ValueError('대사할 은행 거래가 없습니다.')
    return hashlib.sha256(raw).hexdigest(),len(raw),parsed


def import_owner_csv(store, file_path: str | Path) -> dict:
    """별도 소유자 지시로 불변 로컬 대사; 실제 은행 연결로 간주 금지."""
    store.require_permission('company:manage')
    source=Path(file_path)
    fingerprint,byte_count,rows=_load(source)
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        if stopped(con):
            raise PermissionError('비상정지 중 은행 자료 대사 금지')
        if con.execute('SELECT 1 FROM aiwack_bank_reconciliation_batches WHERE source_sha256=?',(fingerprint,)).fetchone():
            raise ValueError('동일 은행 원본을 이미 대사했습니다.')
        linked=[]
        for reference,provider_name,transaction,business,kind,amount,row_sha in rows:
            matched=con.execute('''SELECT id,event_sha256 FROM aiwack_provider_payment_events
                WHERE provider=? AND transaction_id=? AND business_id=?
                  AND event_type=? AND currency='KRW' AND amount_minor=?
                  AND owner_decision='accepted' ''',
                (provider_name,transaction,business,kind,amount)).fetchall()
            if len(matched)!=1:
                raise ValueError('은행 CSV와 관리자 승인 서명 거래 이벤트가 정확히 일치하지 않습니다.')
            event_id,event_sha=matched[0]
            if con.execute('''SELECT 1 FROM aiwack_bank_reconciliation_matches
                            WHERE payment_event_id=? OR bank_reference=?''',(event_id,reference)).fetchone():
                raise ValueError('이미 다른 은행 CSV에 대사된 거래입니다.')
            if any(item[1]==event_id for item in linked):
                raise ValueError('동일 공급자 거래가 CSV에 중복 기록됐습니다.')
            linked.append((reference,int(event_id),event_sha,amount,row_sha))
        batch=int(con.execute('''INSERT INTO aiwack_bank_reconciliation_batches
                (source_sha256,source_bytes,row_count) VALUES(?,?,?)''',
                (fingerprint,byte_count,len(rows))).lastrowid)
        for reference,event_id,event_sha,amount,row_sha in linked:
            con.execute('''INSERT INTO aiwack_bank_reconciliation_matches
                (batch_id,bank_reference,payment_event_id,event_sha256,amount_minor,row_sha256)
                VALUES(?,?,?,?,?,?)''',(batch,reference,event_id,event_sha,amount,row_sha))
    return read(store,batch)


def read(store,batch_id:int)->dict:
    store.require_permission('company:manage')
    if type(batch_id) is not int or batch_id<=0:raise ValueError('은행 대사 ID 형식 오류')
    with store._connect() as con:
        initialize(con)
        batch=con.execute('SELECT source_sha256,source_bytes,row_count FROM aiwack_bank_reconciliation_batches WHERE id=?',(batch_id,)).fetchone()
        if not batch:raise ValueError('은행 대사 기록 없음')
        rows=con.execute('''SELECT m.bank_reference,m.payment_event_id,m.event_sha256,
                    m.amount_minor,p.event_sha256,p.amount_minor,p.owner_decision
                FROM aiwack_bank_reconciliation_matches m
                JOIN aiwack_provider_payment_events p ON p.id=m.payment_event_id
                WHERE m.batch_id=?''',(batch_id,)).fetchall()
    if len(rows)!=batch[2] or any(e!=p or amount!=paid or decision!='accepted'
        for ref,ident,e,amount,p,paid,decision in rows):
        raise ValueError('은행 CSV 대사와 서명 거래 원본의 무결성 오류')
    return {'batch_id':batch_id,'source_sha256':batch[0],'source_bytes':batch[1],
            'matched_signed_events':len(rows),
            'matched_amount_minor':sum(row[3] for row in rows),
            'currency':'KRW','owner_selected_file_matched':True,
            'independent_bank_api_verified':False,
            'independent_provider_verified':False,
            'real_bank_settlement_confirmed':False,
            'actual_payment_or_refund_executed':False}
