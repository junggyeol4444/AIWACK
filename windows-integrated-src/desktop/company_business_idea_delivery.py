"""기존 총괄 GGUF 사업 가설의 관리자 승인형 실제 업무 연결·로컬 결과 검토.

기존 사업/프로젝트/카탈로그/직원 업무 원본을 그대로 사용한다.
업무 생성은 모델 실행이나 상품 출시·게시·결제·고객 발송이 아니다.
"""
from __future__ import annotations

import hashlib
import sqlite3

from desktop.stage87_90_management import stopped
from desktop.company_business_idea_pipeline import (
    _digest, _id, _text, _source, initialize as initialize_pipeline,
)


def initialize(con: sqlite3.Connection) -> None:
    initialize_pipeline(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_idea_delivery_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        idea_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_chief_business_ideas(id),
        business_id INTEGER NOT NULL REFERENCES managed_businesses(id),
        project_id INTEGER NOT NULL REFERENCES managed_business_projects(id),
        catalog_id INTEGER NOT NULL REFERENCES local_catalog_items(id),
        research_task_id INTEGER NOT NULL UNIQUE REFERENCES company_tasks(id),
        product_task_id INTEGER NOT NULL UNIQUE REFERENCES company_tasks(id),
        model_call_id INTEGER NOT NULL REFERENCES ai_model_call_history(id),
        model_output_sha256 TEXT NOT NULL CHECK(length(model_output_sha256)=64),
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 300),
        receipt_sha256 TEXT NOT NULL CHECK(length(receipt_sha256)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK(research_task_id != product_task_id))""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_idea_delivery_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        idea_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_chief_business_ideas(id),
        research_artifact_id INTEGER NOT NULL UNIQUE REFERENCES company_task_artifacts(id),
        product_artifact_id INTEGER NOT NULL UNIQUE REFERENCES company_task_artifacts(id),
        research_artifact_sha256 TEXT NOT NULL CHECK(length(research_artifact_sha256)=64),
        product_artifact_sha256 TEXT NOT NULL CHECK(length(product_artifact_sha256)=64),
        research_model_call_id INTEGER NOT NULL REFERENCES ai_model_call_history(id),
        product_model_call_id INTEGER NOT NULL REFERENCES ai_model_call_history(id),
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 300),
        receipt_sha256 TEXT NOT NULL CHECK(length(receipt_sha256)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK(research_artifact_id != product_artifact_id))""")
    for table in ('aiwack_idea_delivery_tasks', 'aiwack_idea_delivery_reviews'):
        for operation in ('UPDATE', 'DELETE'):
            con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_{operation.lower()}
                BEFORE {operation} ON {table} BEGIN
                SELECT RAISE(ABORT,'실제 모델 상품 업무·관리자 검토 원본 변경 금지'); END""")


def _verified_links(con: sqlite3.Connection, idea_id: int) -> dict:
    from desktop.business_projects import get as get_project
    from desktop.product_catalog import get as get_catalog
    src = _source(con, idea_id)
    p = con.execute("""SELECT business_id,project_id,model_call_id,
        model_output_sha256,owner_note,link_sha256
        FROM aiwack_chief_idea_project_links WHERE idea_id=?""", (idea_id,)).fetchone()
    c = con.execute("""SELECT business_id,project_id,catalog_id,model_call_id,
        model_output_sha256,link_sha256
        FROM aiwack_chief_idea_product_links WHERE idea_id=?""", (idea_id,)).fetchone()
    if p is None or c is None:
        raise PermissionError('실제 모델 가설의 사업·프로젝트·첫 상품 초안을 먼저 연결하세요.')
    business, project, call, sha, note, project_digest = p
    c_business, c_project, catalog, c_call, c_sha, catalog_digest = c
    if (business, call, sha) != (src['business_id'], src['model_call_id'], src['model_output_sha256']):
        raise ValueError('실제 총괄 모델 사업·프로젝트 출처 불일치')
    if (c_business, c_project, c_call, c_sha) != (business, project, call, sha):
        raise ValueError('첫 상품 초안의 실제 총괄 모델 출처 불일치')
    project_payload = dict(idea_id=idea_id, business_id=business, project_id=project,
                           model_call_id=call, model_output_sha256=sha, owner_note=note)
    catalog_payload = dict(idea_id=idea_id, business_id=business, project_id=project,
                           catalog_id=catalog, model_call_id=call, model_output_sha256=sha)
    if _digest(project_payload) != project_digest or _digest(catalog_payload) != catalog_digest:
        raise ValueError('총괄 모델 사업·상품 초안 원본 감사 SHA 불일치')
    model = con.execute('SELECT status FROM ai_model_call_history WHERE id=?', (call,)).fetchone()
    if model is None or model[0] != 'success':
        raise ValueError('실제 총괄 GGUF 호출 성공 원본이 없습니다.')
    project_row = get_project(con, int(project))
    catalog_row = get_catalog(con, int(catalog))
    if project_row['business_id'] != business or (
            catalog_row['business_id'], catalog_row['project_id']) != (business, project):
        raise ValueError('사업·프로젝트·상품 원본 연결 불일치')
    return dict(idea_id=idea_id, business_id=int(business), project_id=int(project),
                catalog_id=int(catalog), model_call_id=int(call), model_output_sha256=sha,
                project=project_row, catalog=catalog_row, source=src)


def _handoff(con: sqlite3.Connection, idea_id: int, linked: dict) -> dict:
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM aiwack_idea_delivery_tasks WHERE idea_id=?',
                      (idea_id,)).fetchone()
    if row is None:
        raise ValueError('관리자가 등록한 조사·제작 업무 인계가 없습니다.')
    result = dict(row)
    payload = {key: result[key] for key in (
        'idea_id','business_id','project_id','catalog_id','research_task_id',
        'product_task_id','model_call_id','model_output_sha256','owner_note')}
    if _digest(payload) != result['receipt_sha256']:
        raise ValueError('조사·제작 업무 인계 SHA 무결성 오류')
    for key in ('business_id','project_id','catalog_id','model_call_id','model_output_sha256'):
        if result[key] != linked[key]:
            raise ValueError('조사·제작 업무와 실제 모델 출처 연결 불일치')
    tasks = (result['research_task_id'], result['product_task_id'])
    actual = {int(row[0]) for row in con.execute(
        'SELECT task_id FROM managed_project_task_links WHERE project_id=?',
        (linked['project_id'],))}
    if not set(tasks).issubset(actual):
        raise ValueError('프로젝트 원본 업무 연결이 누락되었습니다.')
    if not con.execute('SELECT 1 FROM company_task_dependencies WHERE task_id=? AND prerequisite_id=?',
                       (tasks[1], tasks[0])).fetchone():
        raise ValueError('조사 선행 → 제작 후속 업무 연결이 손상되었습니다.')
    return result


def create_owner_work_tasks(store, idea_id: int, research_title: str,
                            product_title: str, owner_note: str) -> dict:
    """별도 관리자 클릭 1회로 실제 미배정 업무 2건과 선행 관계만 등록."""
    store.require_permission('company:manage')
    idea_id = _id(idea_id)
    research_title = _text(research_title, '시장 조사 업무명', 120)
    product_title = _text(product_title, '첫 상품 제작 업무명', 120)
    owner_note = _text(owner_note, '업무 인계 관리자 사유', 300, 5)
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        if stopped(con):
            raise PermissionError('비상정지 중 조사·제작 업무 등록 금지')
        linked = _verified_links(con, idea_id)
        if linked['source']['business_state'] != 'draft' or linked['project']['state'] != 'planned':
            raise PermissionError('사업·프로젝트가 계획 초안 상태일 때만 인계할 수 있습니다.')
        if linked['catalog']['state'] != 'draft' or linked['catalog']['assumed_price_krw'] != 0:
            raise PermissionError('첫 상품이 0원 가정가격의 초안 상태여야 합니다.')
        if con.execute('SELECT 1 FROM aiwack_idea_delivery_tasks WHERE idea_id=?',
                       (idea_id,)).fetchone():
            raise ValueError('이 가설의 조사·제작 업무는 이미 인계됐습니다.')
        src = linked['source']
        descriptions = (
            '관리자 승인형 로컬 시장 조사 업무. 실제 수요 확인 전에는 판매/매출 주장 금지. '
            f"가설: {src['concept'][:250]} / 위험: {src['risk_note'][:180]}",
            '관리자 승인형 로컬 첫 상품 제작 업무. 조사 업무 완료 후 담당 직원 배정·'
            '실제 모델 호출 및 관리자 검수는 별도 수행. '
            f"가설 상품: {src['first_product'][:200]} / 위험: {src['risk_note'][:180]}",
        )
        ids = []
        for title, description in zip((research_title, product_title), descriptions):
            heading, detail, _ = store._task_values(title, description, None)
            task_id = int(con.execute(
                'INSERT INTO company_tasks(plan_id,title,description) VALUES(NULL,?,?)',
                (heading, detail)).lastrowid)
            con.execute("""INSERT INTO company_task_status_events
                (task_id,old_status,new_status) VALUES(?,NULL,'todo')""", (task_id,))
            from desktop.business_projects import set_task_link
            set_task_link(con, linked['project_id'], task_id, True)
            ids.append(task_id)
        con.execute("""INSERT INTO company_task_dependencies(task_id,prerequisite_id)
            VALUES(?,?)""", (ids[1], ids[0]))
        con.execute("""INSERT INTO company_task_dependency_events
            (task_id,prerequisite_id,action) VALUES(?,?,'added')""", (ids[1], ids[0]))
        payload = dict(idea_id=idea_id, business_id=linked['business_id'],
                       project_id=linked['project_id'], catalog_id=linked['catalog_id'],
                       research_task_id=ids[0], product_task_id=ids[1],
                       model_call_id=linked['model_call_id'],
                       model_output_sha256=linked['model_output_sha256'], owner_note=owner_note)
        con.execute("""INSERT INTO aiwack_idea_delivery_tasks
            (idea_id,business_id,project_id,catalog_id,research_task_id,product_task_id,
             model_call_id,model_output_sha256,owner_note,receipt_sha256)
            VALUES(?,?,?,?,?,?,?,?,?,?)""", (*payload.values(), _digest(payload)))
    return {'idea_id': idea_id, 'research_task_id': ids[0],
            'product_task_id': ids[1], 'prerequisite_task_id': ids[0],
            'status': 'todo', 'employee_assigned': False,
            'real_model_executed': False, 'external_actions_executed': False}


def _approved_artifact(con: sqlite3.Connection, task_id: int, artifact_id: int) -> dict:
    row = con.execute("""SELECT a.id,a.task_id,a.body,a.sha256,a.review_status,
        r.model_call_id,r.status,call.status,t.status
        FROM company_task_artifacts a
        JOIN company_task_runs r ON r.id=a.run_id
        JOIN ai_model_call_history call ON call.id=r.model_call_id
        JOIN company_tasks t ON t.id=a.task_id
        WHERE a.id=? AND a.task_id=?""", (artifact_id, task_id)).fetchone()
    if row is None:
        raise ValueError('지정 업무의 실제 직원 모델 결과물이 없습니다.')
    aid, actual_task, body, digest, review_status, call_id, run_status, call_status, task_status = row
    if (review_status != 'approved' or run_status != 'success' or
            call_status != 'success' or task_status != 'done'):
        raise PermissionError('실제 직원 모델 성공·관리자 결과물 승인·업무 완료가 모두 필요합니다.')
    if hashlib.sha256(body.encode('utf-8')).hexdigest() != digest:
        raise ValueError('실제 직원 결과물 SHA 원본 손상')
    if not con.execute("""SELECT 1 FROM company_task_artifact_reviews
        WHERE artifact_id=? AND new_status='approved'""", (artifact_id,)).fetchone():
        raise ValueError('관리자 결과물 승인 감사가 없습니다.')
    return {'artifact_id': int(aid), 'task_id': int(actual_task),
            'artifact_sha256': digest, 'model_call_id': int(call_id)}


def review_local_product(store, idea_id: int, research_artifact_id: int,
                         product_artifact_id: int, owner_note: str) -> dict:
    """실제 직원 2건 승인 후 카탈로그를 내부 검토중으로 전환. 출시는 하지 않음."""
    store.require_permission('company:manage')
    idea_id = _id(idea_id)
    research_artifact_id = _id(research_artifact_id)
    product_artifact_id = _id(product_artifact_id)
    owner_note = _text(owner_note, '관리자 상품 내부 검토 사유', 300, 5)
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        if stopped(con):
            raise PermissionError('비상정지 중 상품 내부 검토 전환 금지')
        linked = _verified_links(con, idea_id)
        handoff = _handoff(con, idea_id, linked)
        if con.execute('SELECT 1 FROM aiwack_idea_delivery_reviews WHERE idea_id=?',
                       (idea_id,)).fetchone():
            raise ValueError('이 가설의 내부 검토는 이미 기록됐습니다.')
        if linked['catalog']['state'] != 'draft' or linked['catalog']['assumed_price_krw'] != 0:
            raise PermissionError('0원 가정가격의 상품 초안만 내부 검토로 전환할 수 있습니다.')
        research = _approved_artifact(con, handoff['research_task_id'], research_artifact_id)
        product = _approved_artifact(con, handoff['product_task_id'], product_artifact_id)
        from desktop.product_catalog import change_state
        change_state(con, linked['catalog_id'], 'review_pending')
        payload = dict(idea_id=idea_id, research_artifact_id=research_artifact_id,
                       product_artifact_id=product_artifact_id,
                       research_artifact_sha256=research['artifact_sha256'],
                       product_artifact_sha256=product['artifact_sha256'],
                       research_model_call_id=research['model_call_id'],
                       product_model_call_id=product['model_call_id'], owner_note=owner_note)
        con.execute("""INSERT INTO aiwack_idea_delivery_reviews
            (idea_id,research_artifact_id,product_artifact_id,research_artifact_sha256,
             product_artifact_sha256,research_model_call_id,product_model_call_id,
             owner_note,receipt_sha256) VALUES(?,?,?,?,?,?,?,?,?)""",
            (*payload.values(), _digest(payload)))
    return {'idea_id': idea_id, 'catalog_id': linked['catalog_id'],
            'catalog_state': 'review_pending', 'owner_internal_review_recorded': True,
            'product_published': False, 'verified_sales': False,
            'external_actions_executed': False}


def history(store, limit: int = 100) -> list[dict]:
    """관리자 읽기 전용 실제 모델→사업→프로젝트→2업무→내부 검토 감사."""
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('업무 인계 감사 조회는 1~200건입니다.')
    with store._connect() as con:
        initialize(con)
        idea_ids = [int(row[0]) for row in con.execute(
            'SELECT idea_id FROM aiwack_idea_delivery_tasks ORDER BY id DESC LIMIT ?',
            (limit,)).fetchall()]
        results = []
        for idea_id in idea_ids:
            linked = _verified_links(con, idea_id)
            handoff = _handoff(con, idea_id, linked)
            review = con.execute('SELECT * FROM aiwack_idea_delivery_reviews WHERE idea_id=?',
                                 (idea_id,)).fetchone()
            review_record = None
            if review is not None:
                review_record = dict(review)
                payload = {key: review_record[key] for key in (
                    'idea_id','research_artifact_id','product_artifact_id',
                    'research_artifact_sha256','product_artifact_sha256',
                    'research_model_call_id','product_model_call_id','owner_note')}
                if _digest(payload) != review_record['receipt_sha256']:
                    raise ValueError('관리자 상품 내부 검토 감사 SHA 불일치')
                for task_key, artifact_key, sha_key, call_key in (
                    ('research_task_id','research_artifact_id','research_artifact_sha256',
                     'research_model_call_id'),
                    ('product_task_id','product_artifact_id','product_artifact_sha256',
                     'product_model_call_id')):
                    a = _approved_artifact(con, handoff[task_key], review_record[artifact_key])
                    if (a['artifact_sha256'], a['model_call_id']) != (
                            review_record[sha_key], review_record[call_key]):
                        raise ValueError('상품 내부 검토 실제 직원 호출·결과물 출처 불일치')
            results.append({
                'idea_id': idea_id, 'business_id': linked['business_id'],
                'project_id': linked['project_id'], 'catalog_id': linked['catalog_id'],
                'research_task_id': handoff['research_task_id'],
                'product_task_id': handoff['product_task_id'],
                'model_call_id': linked['model_call_id'],
                'model_output_sha256': linked['model_output_sha256'],
                'handoff_sha256': handoff['receipt_sha256'],
                'review_sha256': review_record['receipt_sha256'] if review_record else None,
                'catalog_state': linked['catalog']['state'],
                'owner_internal_review_recorded': bool(review_record),
                'product_published': False, 'verified_sales': False,
            })
        return results
