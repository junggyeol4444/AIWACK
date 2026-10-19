"""Stage68: offline, deterministic *human-triggered* prototype artifact creation.

Creates a single static HTML preview from Stage67 catalog metadata, NOT an AI
product, deployable service, release, tested program, or publication. No code
execution, web access, model calls or user-selected filesystem paths.
"""
from __future__ import annotations

import hashlib
from html import escape
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from desktop.business_portfolio import _hash, _id
from desktop.product_catalog import get as get_catalog

STATES = ('prototype', 'review_requested', 'withdrawn')
TRANSITIONS = {'prototype': ('review_requested', 'withdrawn'),
               'review_requested': ('withdrawn',), 'withdrawn': ()}
FIELDS = ('catalog_item_id', 'catalog_version', 'catalog_digest', 'filename',
          'sha256', 'byte_count', 'state')
MAX_ARTIFACT_BYTES = 64 * 1024


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS local_product_prototypes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        catalog_item_id INTEGER NOT NULL REFERENCES local_catalog_items(id) ON DELETE RESTRICT,
        catalog_version INTEGER NOT NULL CHECK(catalog_version > 0),
        catalog_digest TEXT NOT NULL CHECK(length(catalog_digest)=64),
        filename TEXT NOT NULL UNIQUE CHECK(length(filename)=39),
        sha256 TEXT NOT NULL CHECK(length(sha256)=64),
        byte_count INTEGER NOT NULL CHECK(byte_count BETWEEN 1 AND 65536),
        state TEXT NOT NULL DEFAULT 'prototype' CHECK(state IN ('prototype','review_requested','withdrawn')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS local_product_prototype_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prototype_id INTEGER NOT NULL REFERENCES local_product_prototypes(id) ON DELETE RESTRICT,
        action TEXT NOT NULL CHECK(action IN ('created','state_changed')),
        snapshot_json TEXT NOT NULL,
        previous_digest TEXT NOT NULL,
        digest TEXT NOT NULL CHECK(length(digest)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS local_product_prototype_by_catalog ON local_product_prototypes(catalog_item_id,id)')
    con.execute('CREATE INDEX IF NOT EXISTS local_product_prototype_event_by_id ON local_product_prototype_events(prototype_id,id)')
    for table in ('local_product_prototypes', 'local_product_prototype_events'):
        for operation in ('UPDATE', 'DELETE'):
            # Prototype state updates are allowed; identity, file and digest are immutable.
            if table == 'local_product_prototypes' and operation == 'UPDATE':
                continue
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()}
                BEFORE {operation} ON {table} BEGIN
                SELECT RAISE(ABORT,'prototype history is append-only'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS local_product_prototype_identity_guard
        BEFORE UPDATE OF catalog_item_id,catalog_version,catalog_digest,filename,sha256,byte_count
        ON local_product_prototypes BEGIN
        SELECT RAISE(ABORT,'prototype identity is immutable'); END''')


def _digest_catalog(item: dict) -> str:
    keys = ('business_id','project_id','kind','name','description',
            'assumed_price_krw','delivery_note','state','version')
    return _hash({key: item[key] for key in keys})


def render_static_preview(item: dict) -> bytes:
    """Pure, escaped HTML; CSP prevents network resources, scripts and forms."""
    def e(value: object) -> str:
        return escape(str(value), quote=True)
    html = ("<!doctype html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">\n"
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'\">\n"
        '<title>AIWACK 로컬 미출시 시제품</title></head><body>\n'
        '<h1>로컬 미출시 시제품 · AI 제작 아님</h1>\n'
        '<p>이 파일은 관리자가 등록한 미검증 상품 정보를 HTML로 표현한 정적 미리보기입니다. '
        'AI 제작·기능 검증·출시·판매·결제·외부 전송이 아닙니다.</p>\n'
        f'<h2>{e(item["name"])}</h2>\n'
        f'<p>종류: {e(item["kind"])} / 카탈로그 ID: {e(item["id"])} / 버전: {e(item["version"])}</p>\n'
        f'<h3>설명 (미검증)</h3><p>{e(item["description"])}</p>\n'
        f'<h3>제공 계획 (미실행)</h3><p>{e(item["delivery_note"])}</p>\n'
        f'<p>가격 가정 (실거래 아님): {e(item["assumed_price_krw"])} KRW</p>\n'
        '</body></html>\n')
    data = html.encode('utf-8')
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ValueError('시제품 미리보기 크기 제한 초과')
    return data


def artifact_directory(database_path: Path) -> Path:
    return Path(database_path).parent / 'stage68_local_prototypes'


def _path(database_path: Path, filename: str) -> Path:
    if (type(filename) is not str or len(filename) != 39 or
            not filename.startswith('p_') or not filename.endswith('.html') or
            any(c not in '0123456789abcdef' for c in filename[2:-5])):
        raise ValueError('허용되지 않은 시제품 파일명')
    return artifact_directory(database_path) / filename


def _event(con: sqlite3.Connection, prototype_id: int, action: str, snapshot: dict) -> None:
    previous_row = con.execute('''SELECT digest FROM local_product_prototype_events
        WHERE prototype_id=? ORDER BY id DESC LIMIT 1''', (prototype_id,)).fetchone()
    previous = previous_row[0] if previous_row else ''
    digest = _hash({'prototype_id': prototype_id, 'action': action,
                    'snapshot': snapshot, 'previous_digest': previous})
    con.execute('''INSERT INTO local_product_prototype_events
        (prototype_id,action,snapshot_json,previous_digest,digest) VALUES (?,?,?,?,?)''',
        (prototype_id, action, json.dumps(snapshot, ensure_ascii=False, sort_keys=True,
         separators=(',', ':')), previous, digest))


def _snapshot(con: sqlite3.Connection, prototype_id: int) -> dict:
    _id(prototype_id, '시제품')
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM local_product_prototypes WHERE id=?', (prototype_id,)).fetchone()
    if not row:
        raise ValueError('시제품이 존재하지 않습니다.')
    return {k: row[k] for k in FIELDS}


def create(con: sqlite3.Connection, database_path: Path, catalog_item_id: int) -> int:
    item = get_catalog(con, catalog_item_id)  # Verify catalog chain before creation.
    if item['state'] == 'archived':
        raise ValueError('보관된 상품·서비스는 시제품 생성 불가')
    data = render_static_preview(item)
    folder = artifact_directory(database_path)
    if folder.is_symlink():
        raise ValueError('시제품 폴더 심볼릭 링크 사용 불가')
    folder.mkdir(parents=True, exist_ok=True)
    filename = 'p_' + uuid4().hex + '.html'
    destination = _path(database_path, filename)
    # File is never opened for editing or executed. Exclusive creation, no overwrite.
    with destination.open('xb') as output:
        output.write(data)
    try:
        cur = con.execute('''INSERT INTO local_product_prototypes
            (catalog_item_id,catalog_version,catalog_digest,filename,sha256,byte_count)
            VALUES (?,?,?,?,?,?)''', (catalog_item_id, item['version'], _digest_catalog(item),
            filename, hashlib.sha256(data).hexdigest(), len(data)))
        prototype_id = int(cur.lastrowid)
        _event(con, prototype_id, 'created', _snapshot(con, prototype_id))
        return prototype_id
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def get(con: sqlite3.Connection, database_path: Path, prototype_id: int) -> dict:
    snapshot = _snapshot(con, prototype_id)
    con.row_factory = sqlite3.Row
    history = con.execute('''SELECT action,snapshot_json,previous_digest,digest
        FROM local_product_prototype_events WHERE prototype_id=? ORDER BY id''',
        (prototype_id,)).fetchall()
    if not history:
        raise ValueError('시제품 감사 기록 누락')
    previous = ''
    last = None
    for i, row in enumerate(history):
        try:
            snap = json.loads(row['snapshot_json'])
        except (ValueError, TypeError) as exc:
            raise ValueError('시제품 감사 JSON 손상') from exc
        action = row['action']
        expected = _hash({'prototype_id': prototype_id, 'action': action,
                          'snapshot': snap, 'previous_digest': previous})
        if row['previous_digest'] != previous or row['digest'] != expected:
            raise ValueError('시제품 감사 해시 불일치')
        if type(snap) is not dict or set(snap) != set(FIELDS):
            raise ValueError('시제품 감사 필드 불일치')
        if i == 0:
            if action != 'created' or snap['state'] != 'prototype':
                raise ValueError('시제품 생성 이력 불일치')
        elif (action != 'state_changed' or
              snap['state'] not in TRANSITIONS.get(last['state'], ()) or
              any(snap[k] != last[k] for k in FIELDS if k != 'state')):
            raise ValueError('시제품 상태 변경 이력 불일치')
        previous = row['digest']
        last = snap
    if last != snapshot:
        raise ValueError('시제품 현재 상태·감사 기록 불일치')
    item = get_catalog(con, snapshot['catalog_item_id'])
    # Old catalog versions remain valid historical prototypes, but are flagged.
    if item['version'] == snapshot['catalog_version'] and _digest_catalog(item) != snapshot['catalog_digest']:
        raise ValueError('카탈로그 원본 해시 불일치')
    target = _path(database_path, snapshot['filename'])
    if target.parent.is_symlink():
        raise ValueError('시제품 폴더 심볼릭 링크 사용 불가')
    if target.is_symlink() or not target.is_file():
        raise ValueError('시제품 파일이 없거나 심볼릭 링크입니다.')
    if target.stat().st_size != snapshot['byte_count']:
        raise ValueError('시제품 파일 크기 불일치')
    with target.open('rb') as file:
        raw = file.read(MAX_ARTIFACT_BYTES + 1)
    if len(raw) != snapshot['byte_count'] or hashlib.sha256(raw).hexdigest() != snapshot['sha256']:
        raise ValueError('시제품 파일 해시 불일치')
    return {'id': prototype_id, **snapshot, 'artifact_path': str(target),
            'catalog_changed_since_build': item['version'] != snapshot['catalog_version'],
            'created_by_ai': False, 'release_approved': False, 'external_actions_executed': False}


def change_state(con: sqlite3.Connection, database_path: Path,
                 prototype_id: int, state: str) -> dict:
    old = get(con, database_path, prototype_id)
    if type(state) is not str or state not in TRANSITIONS[old['state']]:
        raise ValueError('허용되지 않은 시제품 검토 상태 전환')
    if state == 'review_requested' and old['catalog_changed_since_build']:
        raise ValueError('카탈로그 변경 후 이전 버전 시제품은 검토 요청 불가')
    con.execute('UPDATE local_product_prototypes SET state=? WHERE id=?', (state, prototype_id))
    _event(con, prototype_id, 'state_changed', _snapshot(con, prototype_id))
    return get(con, database_path, prototype_id)


def list_prototypes(con: sqlite3.Connection, database_path: Path,
                    limit: int = 100) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('조회 개수는 1~200입니다.')
    ids = [r[0] for r in con.execute('''SELECT id FROM local_product_prototypes
        ORDER BY id DESC LIMIT ?''', (limit,))]
    return [get(con, database_path, i) for i in ids]


def events(con: sqlite3.Connection, database_path: Path, prototype_id: int) -> list[dict]:
    get(con, database_path, prototype_id)
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute('''SELECT * FROM local_product_prototype_events
        WHERE prototype_id=? ORDER BY id''', (prototype_id,))]
