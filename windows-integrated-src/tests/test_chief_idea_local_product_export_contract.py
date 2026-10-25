"""실제 GGUF 승인 상품의 로컬 파일 보존 계약 — 전체 통합검증 시 실행.

이 테스트는 실제 모델을 호출하거나 성공·판매를 모의하지 않는다.
"""
import sqlite3

import pytest

from desktop.company_business_idea_artifact_export import (
    MAX_EXPORT_BYTES, _safe_path, initialize,
)


class _PathOnlyStore:
    def __init__(self, path):
        self.path = str(path)


def test_export_path_must_remain_inside_local_database_directory(tmp_path):
    store = _PathOnlyStore(tmp_path / 'company.sqlite3')
    name = 'idea_' + 'a' * 32 + '.md'
    assert _safe_path(store, name) == tmp_path / 'aiwack_idea_product_exports' / name
    for bad in ('../company.sqlite3', 'idea_' + 'A' * 32 + '.md',
                'idea_' + 'a' * 31 + '.md', 'idea_' + 'a' * 32 + '.exe',
                'idea_' + 'a' * 32 + '.md/../../other'):
        with pytest.raises(ValueError):
            _safe_path(store, bad)


def test_export_rejects_symlink_folder(tmp_path):
    target = tmp_path / 'actual'
    target.mkdir()
    folder = tmp_path / 'aiwack_idea_product_exports'
    try:
        folder.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('현재 환경에서 디렉터리 심볼릭 링크 생성 불가')
    with pytest.raises(ValueError, match='심볼릭 링크'):
        _safe_path(_PathOnlyStore(tmp_path / 'company.sqlite3'),
                   'idea_' + 'b' * 32 + '.md')


def test_export_schema_is_append_only_and_bounded():
    con = sqlite3.connect(':memory:')
    try:
        initialize(con)
        columns = {row[1]: row[2] for row in con.execute(
            'PRAGMA table_info(aiwack_idea_local_product_exports)')}
        assert {'idea_id','review_id','research_artifact_id','product_artifact_id',
                'filename','file_sha256','byte_count','receipt_sha256'} <= set(columns)
        triggers = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'")}
        assert 'aiwack_idea_local_product_exports_no_update' in triggers
        assert 'aiwack_idea_local_product_exports_no_delete' in triggers
        assert MAX_EXPORT_BYTES == 160 * 1024
    finally:
        con.close()
