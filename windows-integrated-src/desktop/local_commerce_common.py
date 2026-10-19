"""Shared strictly offline validation for synthetic commerce exercises."""
import hashlib
import json
import re

KEY = re.compile(r'[A-Za-z0-9_-]{8,48}\Z', re.ASCII)
ALIAS = re.compile(r'SIMCUST_[A-Za-z0-9_-]{6,32}\Z', re.ASCII)
CURRENCIES = ('KRW','JPY','USD','EUR')
MAX_MINOR = 10**15

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

def ident(value):
    if type(value) is not int or value <= 0: raise ValueError('positive integer ID required')
    return value

def key(value):
    if type(value) is not str or not KEY.fullmatch(value) or any(v in value.lower() for v in ('secret','token','password','bearer','apikey')):
        raise ValueError('non-secret local key 8-48 ASCII characters only')
    return value

def note(value, maximum=240):
    if type(value) is not str or not 1 <= len(value) <= maximum or any(ord(x)<32 or ord(x)==127 for x in value) or '://' in value or '@' in value or any(w in value.lower() for w in ('password','bearer ','api_key')):
        raise ValueError('synthetic note must not include PII, URL, credentials or controls')
    return value

def amount(value):
    if type(value) is not int or not 0 <= value <= MAX_MINOR: raise ValueError('invalid integer minor units')
    return value

def triggers(con, tables):
    for table in tables:
        for operation in ('UPDATE','DELETE'):
            con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'append-only synthetic history'); END""")
