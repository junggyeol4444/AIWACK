"""Stage57 restricted AST execution semantics and safety boundaries."""
import sqlite3
import pytest

from desktop.restricted_code_tests import execute_restricted_tests, RestrictedCodeError
from desktop.storage import LocalStore, AuthenticationError


def owner(tmp_path):
    store = LocalStore(tmp_path / 'owner.sqlite3')
    store.setup_owner('owner57', 'local-owner-57-long-password')
    return store


def test_pure_function_if_and_asserts():
    src = '''FACTOR = 2
def calculate(x):
    if x > 0:
        result = x * FACTOR
        return result
    return 0
'''
    r=execute_restricted_tests(src,'assert calculate(3) == 6\nassert calculate(-2) == 0\nassert calculate(1) == 5')
    assert (r['passed'],r['total'])==(2,3)
    assert [x['passed'] for x in r['results']]==[True,True,False]


@pytest.mark.parametrize('bad', [
    'import os\nx=1',
    'from os import system',
    'open("/tmp/file","w")',
    'x=__import__("os")',
    'a = (1).__class__',
    'x = [n for n in range(10)]',
    'x = [1,2]',
    'while True:\n    pass',
    'for x in (1,2):\n    pass',
    'class Evil:\n    pass',
    'def fn():\n    return eval("1+2")',
    'def fn():\n    exec("pass")',
    'def fn():\n    return x[0]',
    'def fn():\n    yield 1',
    'def fn():\n    global x\n    return 1',
    'def fn():\n    with open("x") as f:\n        pass',
    'def fn(*args):\n    return 1',
    'def fn(a=2):\n    return a',
    '@decorator\ndef fn():\n    return 1',
    'def fn():\n    return lambda x: x',
    'def fn():\n    return f"{secret}"',
    'def fn():\n    return (1).__class__',
])
def test_reject_non_subset_python(bad):
    with pytest.raises((RestrictedCodeError,ValueError)):
        execute_restricted_tests(bad, 'assert True')


@pytest.mark.parametrize('bad',[ 'print("hi")','assert True\nx=2',
    'assert True, "info"','assert 1==1\n'*21,
    'assert __import__("os")','assert open("password.txt")',
    'assert (1).__class__'])
def test_invalid_assertion_code(bad):
    with pytest.raises(RestrictedCodeError):
        execute_restricted_tests('def calculate():\n    return 2\n',bad)


def test_error_handling_no_runaway():
    recursive='def repeat():\n    return repeat()\n'
    r=execute_restricted_tests(recursive,'assert repeat() == 1')
    assert (r['passed'],r['total'])==(0,1) and '재귀' in r['results'][0]['detail']
    r=execute_restricted_tests('def zero():\n    return 1/0\n','assert zero() == 2')
    assert r['passed']==0
    r=execute_restricted_tests('def big():\n    return ' + '*'.join(['10']*50) + '\n','assert big()>0')
    assert r['passed']==0


def test_safe_record_restart_permissions_and_immutability(tmp_path):
    st=owner(tmp_path)
    item=st.save_code_draft('calculation.py','def answer():\n    return 7\n',0)
    r=st.run_restricted_code_tests(item['id'],'assert answer() == 7\nassert answer() == 8')
    assert (r['passed'],r['total'])==(1,2)
    rows=st.list_restricted_code_tests(item['id']);assert rows[0]['status']=='failed'
    with st._connect() as con:
        for query in ('DELETE FROM restricted_code_test_runs','UPDATE restricted_code_test_runs SET status="passed"'):
            with pytest.raises(sqlite3.DatabaseError):con.execute(query)
    st.logout()
    with pytest.raises(AuthenticationError):st.run_restricted_code_tests(item['id'],'assert True')
    st2=LocalStore(tmp_path/'owner.sqlite3')
    with pytest.raises(AuthenticationError):st2.list_restricted_code_tests(item['id'])
    st2.login('owner57','local-owner-57-long-password')
    assert st2.list_restricted_code_tests(item['id'])[0]['status']=='failed'


def test_file_tamper_prevents_test_and_no_history(tmp_path):
    st=owner(tmp_path)
    row=st.save_code_draft('demo.py','def answer():\n    return 7\n',0)
    (tmp_path/'code_drafts'/'demo.py').write_text('def answer():\n    return 999\n')
    with pytest.raises(ValueError):st.run_restricted_code_tests(row['id'],'assert answer() == 7')
    assert st.list_restricted_code_tests(row['id']) == []


def test_disallowed_top_level_has_no_side_effect(tmp_path):
    r=tmp_path/'touch'
    with pytest.raises(RestrictedCodeError):
        execute_restricted_tests('from pathlib import Path\nPath(%r).touch()' % str(r), 'assert True')
    assert not r.exists()
