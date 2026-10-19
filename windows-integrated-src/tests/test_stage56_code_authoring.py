"""Stage56: real local filesystem & SQLite versioning, no code execution."""
import sqlite3
from pathlib import Path
import pytest

from desktop.code_authoring import (_filename, _source, clean_model_reply, generate_local_draft, diff_preview)
from desktop.storage import LocalStore, AuthenticationError


def _owner(tmp_path):
    store=LocalStore(tmp_path/'owner.sqlite3')
    store.setup_owner('testowner','stage56-long-password!')
    return store


def test_create_edit_restart_history_and_filesystem(tmp_path):
    store=_owner(tmp_path)
    first=store.save_code_draft('feature.py','def run():\n    return 1\n',0)
    assert first['version']==1
    assert (tmp_path/'code_drafts'/'feature.py').read_text()=='def run():\n    return 1\n'
    second=store.save_code_draft('feature.py','def run():\n    return 2\n',1,from_model=True)
    assert second['version']==2
    assert [row['version'] for row in store.code_draft_history(first['id'])]==[1,2]
    assert [row['origin'] for row in store.code_draft_history(first['id'])]==['owner_reviewed_draft','local_model_reviewed_draft']
    store.logout();store=LocalStore(tmp_path/'owner.sqlite3')
    with pytest.raises(AuthenticationError):store.list_code_drafts()
    store.login('testowner','stage56-long-password!')
    assert store.read_code_draft(first['id'])['source'].endswith('return 2\n')
    assert len(store.list_code_drafts())==1
    with store._connect() as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('UPDATE local_code_revisions SET source=? WHERE artifact_id=?',('changed',first['id']))


@pytest.mark.parametrize('name',['../escape.py','a/b.py','bad\\folder.py','CON.py','com1.PY','report.txt','foo.py.exe','a-b.py','','é.py'])
def test_windows_invalid_names(name):
    with pytest.raises(ValueError):_filename(name)


@pytest.mark.parametrize('source',['','    def broken(','print(1)\x00','\ud800','x'*32769], ids=['empty','syntax','nul','surrogate','over_max'])
def test_bad_code_rejected(source):
    with pytest.raises(ValueError):_source(source)


def test_no_clobber_or_version_lost_update(tmp_path):
    store=_owner(tmp_path)
    with pytest.raises(ValueError):store.save_code_draft('x.py','x=1\n',2)
    store.save_code_draft('x.py','x=1\n',0)
    for version in (0,2):
        with pytest.raises(ValueError):store.save_code_draft('x.py','x=3\n',version)
    with pytest.raises(ValueError):store.save_code_draft('X.py','x=3\n',0)
    assert store.list_code_drafts()[0]['version']==1


def test_external_file_tamper_blocked(tmp_path):
    store=_owner(tmp_path);item=store.save_code_draft('new.py','a=1\n',0)
    (tmp_path/'code_drafts'/'new.py').write_text('b=2\n')
    with pytest.raises(ValueError,match='일치하지|외부|다릅니다'):
        store.read_code_draft(item['id'])
    with pytest.raises(ValueError,match='외부'):
        store.save_code_draft('new.py','a=3\n',1)


def test_symlink_workspace_and_file_refused(tmp_path):
    store=_owner(tmp_path)
    external=tmp_path/'external.py';external.write_text('x=1\n')
    folder=tmp_path/'code_drafts';folder.mkdir()
    (folder/'unsafe.py').symlink_to(external)
    with pytest.raises(ValueError):store.save_code_draft('unsafe.py','x=3\n',0)
    assert external.read_text()=='x=1\n'
    folder.rmdir() if not list(folder.iterdir()) else (folder/'unsafe.py').unlink()
    folder.rmdir();folder.symlink_to(tmp_path)
    with pytest.raises(PermissionError):store.save_code_draft('hello.py','x=1\n',0)


def test_version_conflict_blocks_external_and_restore(tmp_path):
    store=_owner(tmp_path);item=store.save_code_draft('demo.py','a=1\n',0)
    original=(tmp_path/'code_drafts'/'demo.py').read_bytes()
    with pytest.raises(ValueError):store.save_code_draft('demo.py','this is not python(',1)
    with pytest.raises(ValueError):store.save_code_draft('demo.py','a=1\n',1)
    assert (tmp_path/'code_drafts'/'demo.py').read_bytes()==original
    assert store.code_draft_history(item['id'])[0]['version']==1


def test_code_diff_and_clean_output():
    code=clean_model_reply('```python\ndef answer():\n    return 42\n```')
    assert code.startswith('def answer')
    assert '+    return 42' in diff_preview('def answer():\n    return 1\n',code,'answer.py')
    with pytest.raises(ValueError):clean_model_reply('```python\npass\n```\n```bash\nls\n```')
    with pytest.raises(ValueError):clean_model_reply('```python\nreturn ?\n```')


def test_model_generation_respects_auth_config_and_no_save(monkeypatch,tmp_path):
    store=_owner(tmp_path)
    monkeypatch.setattr(store,'read_local_model',lambda mid: {'name':'test','backend':'llama_cpp',
        'executable_path':'/dummy/local','model_path':'/dummy/model.gguf','max_tokens':90})
    import desktop.code_authoring as ca
    called=[]
    def fake_model(config,prompt,*,timeout):
        called.append((config,prompt,timeout));return '```python\ndef offline():\n    return True\n```'
    monkeypatch.setattr(ca,'run_local_model',fake_model)
    draft=generate_local_draft(store,1,'Make pure Python function')
    assert 'def offline' in draft and called[0][0].backend=='llama_cpp'
    assert not (tmp_path/'code_drafts').exists()  # generation never saves without approval
    store.logout()
    with pytest.raises(AuthenticationError):generate_local_draft(store,1,'code')


def test_no_installed_model_is_honestly_refused(tmp_path):
    store=_owner(tmp_path)
    with pytest.raises(ValueError):generate_local_draft(store,100,'code')
