"""Stage53: physical file I/O, persistence and safe refusal under local owner."""
import os
from pathlib import Path
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from desktop.storage import LocalStore, AuthenticationError
from desktop.managed_documents import MAX_BYTES


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'state.sqlite3')
    store.setup_owner('doc_owner', 'stage53-password-long')
    return store


def test_create_update_real_file_and_revision_history(owner):
    doc_id = owner.create_managed_document('사업계획.md', '첫 번째 문서\n')
    artifact = owner.documents_dir / '사업계획.md'
    assert artifact.is_file() and artifact.read_bytes() == '첫 번째 문서\n'.encode()
    assert owner.read_managed_document(doc_id)['version'] == 1
    assert owner.update_managed_document(doc_id, '수정 후 문서\n', 1) == 2
    assert artifact.read_text('utf-8') == '수정 후 문서\n'
    history = owner.managed_document_revisions(doc_id)
    assert [(r['version'], r['action'], r['content']) for r in history] == [
        (1, 'created', '첫 번째 문서\n'), (2, 'updated', '수정 후 문서\n')]
    owner.logout()
    again = LocalStore(owner.path)
    again.login('doc_owner', 'stage53-password-long')
    assert again.read_managed_document(doc_id)['content'] == '수정 후 문서\n'
    assert again.managed_document_revisions(doc_id) == history


def test_multiple_extensions_and_utf8(owner):
    for name, content in [('readme.txt','한글\n🙂'), ('metrics.csv','name,count\na,2\n'),
                          ('meta.json','{"valid":true}'), ('ideas.md','## 신규 사업')]:
        doc_id=owner.create_managed_document(name,content)
        assert owner.read_managed_document(doc_id)['filename']==name
        assert (owner.documents_dir/name).read_text(encoding='utf-8')==content
    assert len(owner.list_managed_documents())==4


@pytest.mark.parametrize('name', ['','../secret.txt','sub/file.txt','sub\\file.txt','C:\\evil.txt',
                                  '.hidden.md','foo.py','evil.txt.exe','bad space.txt','a..txt',
                                  'a.'+'z'*100+'.txt', 3, None])
def test_reject_unsafe_names(owner,name):
    with pytest.raises(ValueError): owner.create_managed_document(name,'hello')
    assert owner.list_managed_documents()==[]


def test_existing_unmanaged_files_never_overwritten(owner):
    owner.documents_dir.mkdir()
    path=owner.documents_dir/'notes.txt'
    path.write_text('기존 사용자 파일',encoding='utf-8')
    with pytest.raises(ValueError,match='이미'):owner.create_managed_document('notes.txt','새 내용')
    assert path.read_text(encoding='utf-8')=='기존 사용자 파일'


def test_collision_and_conflicting_version(owner):
    ident=owner.create_managed_document('Report.TXT','one')
    with pytest.raises(ValueError):owner.create_managed_document('report.txt','two')
    assert owner.update_managed_document(ident,'two',1)==2
    with pytest.raises(ValueError,match='먼저'):owner.update_managed_document(ident,'three',1)
    with pytest.raises(ValueError,match='없습니다'):owner.update_managed_document(ident,'two',2)
    assert owner.read_managed_document(ident)['content']=='two'


def test_external_edits_block_read_and_update_without_clobber(owner):
    ident=owner.create_managed_document('notes.txt','managed')
    target=owner.documents_dir/'notes.txt'
    target.write_text('unexpected outsider',encoding='utf-8')
    with pytest.raises(ValueError,match='일치'):owner.read_managed_document(ident)
    with pytest.raises(ValueError,match='외부'):owner.update_managed_document(ident,'override',1)
    assert target.read_text()=='unexpected outsider'
    assert len(owner.managed_document_revisions(ident))==1


def test_remove_external_file_blocks_update_and_preserves_audit(owner):
    ident=owner.create_managed_document('lost.txt','stored')
    (owner.documents_dir/'lost.txt').unlink()
    with pytest.raises(ValueError,match='없어'):owner.update_managed_document(ident,'new',1)
    assert owner.managed_document_revisions(ident)[0]['content']=='stored'


def test_symlink_and_hardlink_refused(owner,tmp_path):
    ident=owner.create_managed_document('safe.txt','data')
    target=owner.documents_dir/'safe.txt'
    external=tmp_path/'external.txt'
    external.write_text('private',encoding='utf-8')
    target.unlink()
    try:
        target.symlink_to(external)
    except (OSError,NotImplementedError):
        pytest.skip('symlinks unavailable')
    with pytest.raises(PermissionError):owner.update_managed_document(ident,'hijack',1)
    with pytest.raises(PermissionError):owner.read_managed_document(ident)
    assert external.read_text()=='private'
    target.unlink()
    os.link(external,target)
    with pytest.raises(PermissionError):owner.update_managed_document(ident,'hijack',1)
    assert external.read_text()=='private'


def test_symlink_workspace_blocked(owner,tmp_path):
    other=tmp_path/'elsewhere'
    other.mkdir()
    try:
        owner.documents_dir.symlink_to(other,target_is_directory=True)
    except (OSError,NotImplementedError):pytest.skip('symlinks unavailable')
    with pytest.raises(PermissionError):owner.create_managed_document('danger.txt','hello')
    assert list(other.iterdir())==[]


def test_bad_content_size_type_ids_and_nul(owner):
    for bad in ('a'*(MAX_BYTES+1),'🙂'*(MAX_BYTES//4+1),'hi\x00no', None, 17):
        with pytest.raises(ValueError):owner.create_managed_document('big.txt',bad)
    ident=owner.create_managed_document('small.txt','safe')
    for bad in (0, True, -1, '1', 9999):
        with pytest.raises(ValueError):owner.read_managed_document(bad)
    for version in (0, True, '1', -2):
        with pytest.raises(ValueError):owner.update_managed_document(ident,'new',version)
    assert owner.read_managed_document(ident)['content']=='safe'


def test_owner_required_for_all_document_operations(owner):
    ident=owner.create_managed_document('secure.txt','abc')
    owner.logout()
    for action in (lambda:owner.create_managed_document('a.txt','a'),
                   lambda:owner.update_managed_document(ident,'xyz',1),
                   lambda:owner.list_managed_documents(),
                   lambda:owner.read_managed_document(ident),
                   lambda:owner.managed_document_revisions(ident)):
        with pytest.raises(AuthenticationError):action()


def test_revision_immutable_sqlite(owner):
    ident=owner.create_managed_document('history.txt','v1')
    owner.update_managed_document(ident,'v2',1)
    with sqlite3.connect(owner.path) as con:
        for statement in ('DELETE FROM managed_document_revisions WHERE document_id=?',
                          'UPDATE managed_document_revisions SET content="bad" WHERE document_id=?',
                          'DELETE FROM managed_documents WHERE id=?'):
            with pytest.raises(sqlite3.IntegrityError):con.execute(statement,(ident,))


def test_concurrent_updates_exactly_one_wins(owner):
    ident=owner.create_managed_document('concurrent.txt','v1')
    def writer(content):
        try:
            return owner.update_managed_document(ident,content,1)
        except ValueError:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(writer,['v2a','v2b']))
    assert sorted(results,key=str)==sorted([2,'conflict'],key=str)
    assert owner.read_managed_document(ident)['version']==2
    assert len(owner.managed_document_revisions(ident))==2


def test_no_network_or_subprocess(monkeypatch,owner):
    import socket,subprocess
    def forbidden(*args,**kwargs):raise AssertionError('network or process execution forbidden')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    ident=owner.create_managed_document('offline.md','no external calls')
    owner.update_managed_document(ident,'offline update',1)
    assert owner.read_managed_document(ident)['content']=='offline update'
