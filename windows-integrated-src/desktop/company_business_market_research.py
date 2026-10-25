"""총괄 GGUF 사업 가설에 실제 공개 HTTPS 조사 출처를 연결한다.

기존 로컬 Windows EXE의 직접 소유자 승인, 공개 DNS 고정 TLS GET,
SQLite 출처/원문 해시 감사만 사용한다. 검색 결과·시장 수요·사업 매출을
만들어 내거나 API 계정 로그인, 숨겨진 크롤링·결제를 실행하지 않는다.
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading

from desktop.stage87_90_management import stopped


def initialize(con: sqlite3.Connection) -> None:
    from desktop.research_captures import initialize as init_capture
    from desktop.public_web_research import initialize as init_receipt
    from desktop.company_business_ideas_model import initialize as init_ideas
    init_capture(con)
    init_receipt(con)
    init_ideas(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_business_source_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        idea_id INTEGER NOT NULL REFERENCES aiwack_chief_business_ideas(id)
            ON DELETE RESTRICT,
        capture_id INTEGER NOT NULL REFERENCES offline_research_captures(id)
            ON DELETE RESTRICT,
        source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64),
        raw_sha256 TEXT NOT NULL CHECK(length(raw_sha256)=64),
        owner_confirmed INTEGER NOT NULL CHECK(owner_confirmed=1),
        source_verified INTEGER NOT NULL DEFAULT 0 CHECK(source_verified=0),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(idea_id,capture_id))""")
    con.execute("""CREATE INDEX IF NOT EXISTS aiwack_business_source_by_idea
        ON aiwack_business_source_links(idea_id,id DESC)""")
    for verb in ('UPDATE','DELETE'):
        con.execute(f"""CREATE TRIGGER IF NOT EXISTS aiwack_business_source_no_{verb.lower()}
            BEFORE {verb} ON aiwack_business_source_links
            BEGIN SELECT RAISE(ABORT,'사업 조사 원본 출처 연결 삭제·수정 금지'); END""")


def _id(value):
    if type(value) is not int or value<=0:
        raise ValueError('실제 총괄 AI 사업 가설 번호가 필요합니다.')
    return value


def _idea_exists(con, idea_id):
    if not con.execute("""SELECT 1 FROM aiwack_chief_business_ideas
        WHERE id=?""",(idea_id,)).fetchone():
        raise ValueError('실제 총괄 GGUF 사업 가설 원본이 없습니다.')


def capture_source(store, idea_id: int, url: str, hostname: str,
                   title: str, *, owner_confirmed: bool=False,
                   cancel: threading.Event | None=None) -> dict:
    """Owner-selected single real HTTPS GET with immutable business link.

    No external write. The remote document remains independently unverified,
    and HTML is inert text in the existing capture store.
    """
    store.require_permission('company:manage')
    _id(idea_id)
    if owner_confirmed is not True:
        raise PermissionError('관리자가 정확한 자료 URL을 선택·확인해야 합니다.')
    if type(title) is not str or not 1<=len(title.strip())<=200:
        raise ValueError('실제 조사 자료 제목은 1~200자여야 합니다.')
    from desktop.public_web_research import read_public_https, save_success
    with store._connect() as con:
        initialize(con)
        if stopped(con):
            raise PermissionError('회사 비상정지 중 외부 공개자료 요청 금지')
        _idea_exists(con,idea_id)
    if cancel is not None and cancel.is_set():
        raise InterruptedError('공개 자료 수집 시작 전 관리자 취소')
    # Public-only, pinned DNS, TLS-hostname check, max 128KiB, no redirect,
    # scripts, credentials, provider mutation or cloud-model usage.
    result=read_public_https(url,hostname,consent=True,timeout=6)
    if cancel is not None and cancel.is_set():
        raise InterruptedError('관리자가 외부 자료 수집 결과 저장을 취소했습니다.')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        if stopped(con) or (cancel is not None and cancel.is_set()):
            raise InterruptedError('자료 수집 중 관리자 취소 또는 비상정지')
        _idea_exists(con,idea_id)
        # Reuse only an existing genuine HTTPS response with exactly the same
        # URL and raw bytes. Never reuse a manual offline snapshot as a GET.
        existing=con.execute("""SELECT r.capture_id,c.content_sha256
            FROM public_web_research_receipts r
            JOIN offline_research_captures c ON c.id=r.capture_id
            WHERE c.source_url=? AND r.raw_sha256=? LIMIT 1""",
            (result['url'],result['raw_sha256'])).fetchone()
        if existing:
            capture_id=int(existing[0])
            content_sha=existing[1]
        else:
            saved=save_success(con,result,title.strip())
            capture_id=int(saved['capture_id'])
            row=con.execute("""SELECT content_sha256 FROM offline_research_captures
                WHERE id=?""",(capture_id,)).fetchone()
            content_sha=row[0]
        if con.execute("""SELECT 1 FROM aiwack_business_source_links
            WHERE idea_id=? AND capture_id=?""",
            (idea_id,capture_id)).fetchone():
            return {'idea_id':idea_id,'capture_id':capture_id,
                    'existing_verified_capture_reused':bool(existing),
                    'already_linked':True,'source_verified':False}
        link_id=int(con.execute("""INSERT INTO aiwack_business_source_links
            (idea_id,capture_id,source_sha256,raw_sha256,owner_confirmed)
            VALUES(?,?,?,?,1)""",
            (idea_id,capture_id,content_sha,result['raw_sha256'])).lastrowid)
    return {'id':link_id,'idea_id':idea_id,'capture_id':capture_id,
            'actual_https_get':True,'raw_sha256':result['raw_sha256'],
            'source_content_sha256':content_sha,
            'existing_verified_capture_reused':bool(existing),
            'source_verified':False,'market_demand_verified':False,
            'customer_orders':0,'external_actions_executed':False}


def history(store, idea_id: int, limit: int=50) -> list[dict]:
    """Trace captured URL and real response hash to an actual chief idea."""
    store.require_permission('company:manage')
    _id(idea_id)
    if type(limit) is not int or not 1<=limit<=200:
        raise ValueError('사업 공개 조사 근거 조회는 1~200건입니다.')
    with store._connect() as con:
        initialize(con)
        _idea_exists(con,idea_id)
        rows=con.execute("""SELECT l.id,l.idea_id,l.capture_id,
                c.source_url,c.title,l.source_sha256,l.raw_sha256,
                r.hostname,r.http_status,l.source_verified,l.created_at
            FROM aiwack_business_source_links l
            JOIN offline_research_captures c ON c.id=l.capture_id
            JOIN public_web_research_receipts r ON r.capture_id=l.capture_id
            WHERE l.idea_id=? ORDER BY l.id DESC LIMIT ?""",
            (idea_id,limit)).fetchall()
    names=('link_id','idea_id','capture_id','source_url','source_title',
           'content_sha256','raw_sha256','hostname','http_status',
           'source_verified','created_at')
    return [dict(zip(names,row)) for row in rows]
