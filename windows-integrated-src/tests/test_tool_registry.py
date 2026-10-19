"""Stage51: metadata-only catalog with persisted audit and authentication."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest

from desktop.storage import LocalStore, AuthenticationError
from desktop.tool_registry import CATEGORIES


@pytest.fixture
def store(tmp_path):
    obj = LocalStore(tmp_path / 'tools.sqlite3')
    obj.setup_owner('owner51', 'stage51-owner-password')
    return obj


def add(store, key='local_file_reader', category='file', permission=''):
    return store.register_ai_tool(key, '로컬 파일 읽기 후보', category, '등록만 된 도구 메타데이터', permission)


def test_register_list_read_persist_and_audit(store):
    tid = add(store)
    assert store.read_registered_ai_tool(tid)['state'] == 'registered'
    assert store.list_registered_ai_tools()[0]['tool_key'] == 'local_file_reader'
    assert [x['event'] for x in store.registered_ai_tool_audit(tid)] == ['registered']
    store.logout()
    other = LocalStore(store.path)
    with pytest.raises(AuthenticationError):other.list_registered_ai_tools()
    other.login('owner51', 'stage51-owner-password')
    assert other.read_registered_ai_tool(tid)['name'] == '로컬 파일 읽기 후보'


def test_archive_preserves_history_and_requires_reason(store):
    tid = add(store)
    with pytest.raises(ValueError):store.retire_registered_ai_tool(tid,'')
    assert store.retire_registered_ai_tool(tid,'운영자가 사용 계획을 철회') is True
    assert store.list_registered_ai_tools() == []
    assert store.read_registered_ai_tool(tid)['state'] == 'retired'
    assert [a['event'] for a in store.registered_ai_tool_audit(tid)] == ['registered','retired']
    with pytest.raises(ValueError):store.retire_registered_ai_tool(tid,'중복')
    with pytest.raises(ValueError):add(store)


@pytest.mark.parametrize('key', ['', 'a', 'A_file', 'space in name', '../escape', '한글명', 'a'*65, None, 42])
def test_reject_invalid_keys(store, key):
    with pytest.raises(ValueError):add(store,key=key)


@pytest.mark.parametrize('category', ['shell', 'api', 'FILE', '', None])
def test_reject_unsupported_categories(store, category):
    with pytest.raises(ValueError):add(store,category=category)


@pytest.mark.parametrize('capability', ['unknown', 1, 'company:write', None])
def test_reject_unknown_capabilities(store, capability):
    with pytest.raises(ValueError):add(store,permission=capability)


def test_known_capability_is_metadata_not_employee_grant(store):
    tid = add(store,permission='company:read')
    assert store.read_registered_ai_tool(tid)['required_capability'] == 'company:read'
    assert store.list_employee_records() == []
    assert store.list_registered_ai_tools()  # No executor objects or external process initiated.


def test_all_categories_supported_and_defaults_metadata_only(store):
    for index,category in enumerate(CATEGORIES):
        store.register_ai_tool(f'candidate_{index:02}',f'후보 {index}',category,'설명')
    assert len(store.list_registered_ai_tools()) == len(CATEGORIES)
    assert all(t['state']=='registered' for t in store.list_registered_ai_tools())


def test_unauthed_denies_all_reads_and_writes(store):
    tid=add(store)
    store.logout()
    calls=(lambda:store.register_ai_tool('x123','이름','file','설명'),
           lambda:store.list_registered_ai_tools(),
           lambda:store.read_registered_ai_tool(tid),
           lambda:store.retire_registered_ai_tool(tid,'사유'),
           lambda:store.registered_ai_tool_audit(tid))
    for call in calls:
        with pytest.raises(AuthenticationError):call()


def test_database_guard_prevents_untracked_mutation(store):
    tid=add(store)
    with sqlite3.connect(store.path) as con:
        for sql in ("UPDATE tool_registry SET name='tampered' WHERE id=?",
                    'DELETE FROM tool_registry WHERE id=?',
                    "UPDATE tool_registry_audit SET reason='tampered' WHERE tool_id=?",
                    'DELETE FROM tool_registry_audit WHERE tool_id=?'):
            with pytest.raises(sqlite3.IntegrityError):con.execute(sql,(tid,))


def test_concurrent_duplicate_registration_exactly_one(store):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _: _try_add(store), range(2)))
    assert sorted(results)==['duplicate','ok']
    assert len(store.list_registered_ai_tools())==1


def _try_add(store):
    try:
        add(store)
        return 'ok'
    except ValueError:
        return 'duplicate'


def test_invalid_limits_and_ids(store):
    with pytest.raises(ValueError):store.list_registered_ai_tools(limit=0)
    with pytest.raises(ValueError):store.read_registered_ai_tool(True)
    with pytest.raises(ValueError):store.registered_ai_tool_audit(123456)
    with pytest.raises(ValueError):store.retire_registered_ai_tool(3,'사유')


def test_no_network_or_process_execution(monkeypatch,store):
    import socket,subprocess
    monkeypatch.setattr(socket.socket,'connect',lambda *args: (_ for _ in ()).throw(AssertionError('network')))
    monkeypatch.setattr(subprocess,'Popen',lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError('process')))
    tid=add(store)
    assert store.retire_registered_ai_tool(tid,'등록 취소')
