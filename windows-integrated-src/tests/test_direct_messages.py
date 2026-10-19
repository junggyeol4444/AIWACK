import sqlite3
import pytest
from desktop.storage import LocalStore,AuthenticationError

@pytest.fixture
def store(tmp_path):
    s=LocalStore(tmp_path/'messages.sqlite3')
    s.setup_owner('owner41','secure-stage41-password')
    return s

def add_two(s):
    # Keep employee creation through the existing public API.
    a=s.add_employee_draft('sender41','Sender')
    b=s.add_employee_draft('receiver41','Receiver')
    return a,b

def test_persistence_and_read(store):
    a,b=add_two(store)
    mid=store.send_direct_message(a,b,'Subject','Body')
    assert store.list_direct_messages(b)[0]['body']=='Body'
    assert store.mark_direct_message_read(mid) is True
    assert store.mark_direct_message_read(mid) is False
    store.logout()
    other=LocalStore(store.path)
    other.login('owner41','secure-stage41-password')
    assert other.list_direct_messages()[0]['read_at'] is not None
    with sqlite3.connect(store.path) as con:
        assert con.execute('PRAGMA foreign_key_check').fetchall()==[]

def test_validation_and_auth(store):
    a,b=add_two(store)
    for x,y,subject,body in ((a,a,'s','b'),(a,999,'s','b'),(a,b,'','b'),(a,b,'s','')):
        with pytest.raises(ValueError):
            store.send_direct_message(x,y,subject,body)
    store.logout()
    with pytest.raises(AuthenticationError):
        store.list_direct_messages()
