"""실제 총괄 GGUF 가설 → 관리자 선택 → 기존 사업/프로젝트/상품 초안 연결.

기존 SQLite 및 Windows Tk 프로그램의 기능 확장. 모델이 제안한 가설은
시장 검증·상품 완성·매출 증빙이 아니다. 매 단계는 관리자가 별도 실행한다.
외부 계정·결제·게시·발송·실행 권한을 이 모듈에 부여하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from desktop.stage87_90_management import stopped
from desktop.company_business_ideas_model import initialize as initialize_ideas


def _digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()


def _id(value: int) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError('실제 모델 가설 번호는 양의 정수여야 합니다.')
    return value


def _text(value: str, label: str, maximum: int, minimum: int = 1) -> str:
    if type(value) is not str or not minimum <= len(value.strip()) <= maximum:
        raise ValueError(f'{label}은 {minimum}~{maximum}자여야 합니다.')
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f'{label}에 제어 문자를 넣을 수 없습니다.')
    return value.strip()


def initialize(con: sqlite3.Connection) -> None:
    initialize_ideas(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_chief_idea_project_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        idea_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_chief_business_ideas(id),
        business_id INTEGER NOT NULL REFERENCES managed_businesses(id),
        project_id INTEGER NOT NULL UNIQUE REFERENCES managed_business_projects(id),
        model_call_id INTEGER NOT NULL REFERENCES ai_model_call_history(id),
        model_output_sha256 TEXT NOT NULL CHECK(length(model_output_sha256)=64),
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 300),
        link_sha256 TEXT NOT NULL CHECK(length(link_sha256)=64),
        recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_chief_idea_product_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        idea_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_chief_business_ideas(id),
        business_id INTEGER NOT NULL REFERENCES managed_businesses(id),
        project_id INTEGER NOT NULL REFERENCES managed_business_projects(id),
        catalog_id INTEGER NOT NULL UNIQUE REFERENCES local_catalog_items(id),
        model_call_id INTEGER NOT NULL REFERENCES ai_model_call_history(id),
        model_output_sha256 TEXT NOT NULL CHECK(length(model_output_sha256)=64),
        link_sha256 TEXT NOT NULL CHECK(length(link_sha256)=64),
        recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    for table in ('aiwack_chief_idea_project_links', 'aiwack_chief_idea_product_links'):
        for operation in ('UPDATE', 'DELETE'):
            con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_{operation.lower()}
                BEFORE {operation} ON {table} BEGIN
                SELECT RAISE(ABORT,'총괄 실제 모델 사업 초안 연결 원본 변경 금지'); END""")


def _source(con: sqlite3.Connection, idea_id: int) -> dict:
    row = con.execute("""SELECT i.id, i.concept, i.first_product, i.risk_note,
        d.business_id, d.model_call_id, d.model_output_sha256, b.state,
        a.output_sha256, a.parsed, decision.decision
        FROM aiwack_chief_business_ideas i
        JOIN aiwack_chief_business_idea_drafts d ON d.idea_id=i.id
        JOIN aiwack_chief_business_idea_attempts a ON a.id=i.attempt_id
        JOIN aiwack_chief_business_idea_decisions decision ON decision.idea_id=i.id
        JOIN managed_businesses b ON b.id=d.business_id
        WHERE i.id=?""", (idea_id,)).fetchone()
    if row is None or row[9] != 1 or row[10] != 'shortlisted':
        raise PermissionError('실제 모델 출처가 있고 관리자가 후보 선정·사업 초안 등록한 가설만 연결합니다.')
    if row[6] != row[8]:
        raise ValueError('사업 초안의 실제 GGUF 출력 해시 불일치')
    return dict(zip(('idea_id','concept','first_product','risk_note','business_id',
                     'model_call_id','model_output_sha256','business_state',
                     'attempt_sha256','parsed','decision'), row))


def create_project_draft(store, idea_id: int, title: str, owner_note: str) -> dict:
    """관리자 별도 클릭으로 예산 0원 프로젝트만 작성한다."""
    store.require_permission('company:manage')
    idea_id = _id(idea_id)
    title = _text(title, '관리자 프로젝트명', 120)
    owner_note = _text(owner_note, '관리자 계획 검토 사유', 300, 5)
    from desktop.business_portfolio import initialize as init_business
    from desktop.business_projects import initialize as init_projects, create as create_project
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        init_business(con)
        init_projects(con)
        initialize(con)
        if stopped(con):
            raise PermissionError('비상정지 중 프로젝트 초안 생성 금지')
        src = _source(con, idea_id)
        if src['business_state'] != 'draft':
            raise PermissionError('초안 상태의 사업에만 실제 모델 프로젝트 초안을 연결합니다.')
        if con.execute('SELECT 1 FROM aiwack_chief_idea_project_links WHERE idea_id=?',
                       (idea_id,)).fetchone():
            raise ValueError('이 가설의 프로젝트 초안은 이미 연결됐습니다.')
        project_id = create_project(con, src['business_id'], title, src['concept'],
                                    planned_budget_krw=0)
        payload = dict(idea_id=idea_id, business_id=src['business_id'],
                       project_id=project_id, model_call_id=src['model_call_id'],
                       model_output_sha256=src['model_output_sha256'], owner_note=owner_note)
        con.execute("""INSERT INTO aiwack_chief_idea_project_links
            (idea_id,business_id,project_id,model_call_id,model_output_sha256,owner_note,link_sha256)
            VALUES (?,?,?,?,?,?,?)""",
            (idea_id,src['business_id'],project_id,src['model_call_id'],
             src['model_output_sha256'],owner_note,_digest(payload)))
    return {'idea_id':idea_id,'business_id':src['business_id'],'project_id':project_id,
            'state':'planned','planned_budget_krw':0,'owner_action_recorded':True,
            'external_actions_executed':False}


def create_product_draft(store, idea_id: int, kind: str, product_name: str,
                         delivery_note: str) -> dict:
    """관리자가 2차로 승인할 때만 기존 상품 카탈로그에 0원 초안 연결."""
    store.require_permission('company:manage')
    idea_id = _id(idea_id)
    if kind not in ('product','service'):
        raise ValueError('상품 유형은 product 또는 service여야 합니다.')
    product_name = _text(product_name,'관리자 상품명',120)
    delivery_note = _text(delivery_note,'상품 제공 계획',400)
    from desktop.business_portfolio import initialize as init_business
    from desktop.business_projects import initialize as init_projects, get as get_project
    from desktop.product_catalog import initialize as init_catalog, create as create_catalog
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        init_business(con)
        init_projects(con)
        init_catalog(con)
        initialize(con)
        if stopped(con):
            raise PermissionError('비상정지 중 상품 초안 생성 금지')
        src = _source(con, idea_id)
        if src['business_state'] != 'draft':
            raise PermissionError('사업 초안 상태에서만 상품 초안을 연결합니다.')
        project_row = con.execute("""SELECT business_id,project_id FROM
            aiwack_chief_idea_project_links WHERE idea_id=?""",(idea_id,)).fetchone()
        if project_row is None or int(project_row[0]) != src['business_id']:
            raise PermissionError('관리자가 먼저 실제 모델 가설의 프로젝트 초안을 연결해야 합니다.')
        project_id = int(project_row[1])
        project = get_project(con, project_id)
        if project['state'] != 'planned' or project['business_id'] != src['business_id']:
            raise PermissionError('계획 중인 동일 사업 프로젝트만 상품 초안을 생성할 수 있습니다.')
        if con.execute('SELECT 1 FROM aiwack_chief_idea_product_links WHERE idea_id=?',
                       (idea_id,)).fetchone():
            raise ValueError('이 가설의 첫 상품 초안은 이미 연결됐습니다.')
        description = '실제 GGUF 미검증 첫 상품 가설: ' + src['first_product'] + '\n위험: ' + src['risk_note']
        catalog_id = create_catalog(con, src['business_id'], kind, product_name,
                                    description, 0, delivery_note, project_id=project_id)
        payload = dict(idea_id=idea_id,business_id=src['business_id'],
                       project_id=project_id,catalog_id=catalog_id,
                       model_call_id=src['model_call_id'],
                       model_output_sha256=src['model_output_sha256'])
        con.execute("""INSERT INTO aiwack_chief_idea_product_links
            (idea_id,business_id,project_id,catalog_id,model_call_id,model_output_sha256,link_sha256)
            VALUES (?,?,?,?,?,?,?)""",
            (idea_id,src['business_id'],project_id,catalog_id,src['model_call_id'],
             src['model_output_sha256'],_digest(payload)))
    return {'idea_id':idea_id,'business_id':src['business_id'],'project_id':project_id,
            'catalog_id':catalog_id,'state':'draft','assumed_price_krw':0,
            'owner_action_recorded':True,'actual_product_completed':False,
            'external_actions_executed':False}


def history(store, limit: int = 100) -> list[dict]:
    """기존 사업·프로젝트·상품 감사 사슬을 포함한 연결 출처 조회."""
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('실제 모델 사업 초안 연결 조회는 1~200건입니다.')
    from desktop.business_portfolio import initialize as init_business
    from desktop.business_projects import initialize as init_projects, get as get_project
    from desktop.product_catalog import initialize as init_catalog, get as get_catalog
    with store._connect() as con:
        init_business(con)
        init_projects(con)
        init_catalog(con)
        initialize(con)
        rows=con.execute("""SELECT i.id,p.business_id,p.project_id,p.model_call_id,
            p.model_output_sha256,p.owner_note,p.link_sha256,
            c.catalog_id,c.link_sha256,c.model_call_id,c.model_output_sha256
            FROM aiwack_chief_business_ideas i
            JOIN aiwack_chief_idea_project_links p ON p.idea_id=i.id
            LEFT JOIN aiwack_chief_idea_product_links c ON c.idea_id=i.id
            ORDER BY i.id DESC LIMIT ?""",(limit,)).fetchall()
        result=[]
        for row in rows:
            idea,business,project,call,sha,note,digest,catalog,c_digest,c_call,c_sha=row
            src=_source(con,int(idea))
            payload=dict(idea_id=idea,business_id=business,project_id=project,
                         model_call_id=call,model_output_sha256=sha,owner_note=note)
            if _digest(payload)!=digest or src['business_id']!=business or (
                    src['model_call_id'],src['model_output_sha256'])!=(call,sha):
                raise ValueError('실제 GGUF 사업 프로젝트 연결 감사 무결성 오류')
            checked_project=get_project(con,int(project))
            if checked_project['business_id']!=business:
                raise ValueError('사업 프로젝트 연결 불일치')
            if catalog is not None:
                product_payload=dict(idea_id=idea,business_id=business,project_id=project,
                                     catalog_id=catalog,model_call_id=c_call,
                                     model_output_sha256=c_sha)
                if _digest(product_payload)!=c_digest or (c_call,c_sha)!=(call,sha):
                    raise ValueError('실제 GGUF 첫 상품 연결 감사 무결성 오류')
                checked_catalog=get_catalog(con,int(catalog))
                if (checked_catalog['business_id'],checked_catalog['project_id'])!=(business,project):
                    raise ValueError('사업 상품 연결 불일치')
            result.append({'idea_id':idea,'business_id':business,'project_id':project,
                           'catalog_id':catalog,'model_call_id':call,
                           'model_output_sha256':sha,'project_link_sha256':digest,
                           'product_link_sha256':c_digest,
                           'project_state':checked_project['state'],
                           'catalog_state':checked_catalog['state'] if catalog is not None else None,
                           'verified_market_data':False,'verified_sales':False})
        return result
