"""Offline import of actual plugin envelopes (not authenticated RPC)."""
import json
import sqlite3
import pytest
from desktop.public_site_crawler import load_plugin_export
from desktop.storage import LocalStore
URL='https://docs.python.org/3/library/urllib.request.html'


def store(tmp_path):
    s=LocalStore(tmp_path/'business.sqlite3')
    s.setup_owner('owner','example-admin-password')
    return s


def test_tinyfish_unmodified_text_envelope_can_be_imported(tmp_path):
    native={'results':[{'url':URL,'title':'urllib.request docs','text':'A real public URL was retrieved by the chat connector.'}]}
    raw=json.dumps({'provider':'tinyfish','tool_result':{'text':json.dumps(native)}}).encode()
    provider, records=load_plugin_export(raw)
    assert provider=='tinyfish' and records[0]['url']==URL
    s=store(tmp_path)
    receipt=s.import_web_plugin_export(raw)
    assert len(receipt['capture_ids'])==1 and receipt['source_verified'] is False
    with sqlite3.connect(s.path) as con:
        row=con.execute('SELECT provider,provenance FROM public_plugin_imports').fetchone()
        assert row==('tinyfish','locally_imported_external_claim')


def test_firecrawl_scrape_data_payload_can_be_imported(tmp_path):
    raw=json.dumps({'provider':'firecrawl','tool_result':{'data':{'markdown':'# Example extracted markdown','metadata':{'sourceURL':URL,'title':'Fetch'}}}}).encode()
    provider,records=load_plugin_export(raw)
    assert records[0]=={'url':URL,'title':'Fetch','text':'# Example extracted markdown'}
    assert store(tmp_path).import_web_plugin_export(raw)['source_verified'] is False


def test_tavily_results_payload_can_be_imported(tmp_path):
    raw=json.dumps({'provider':'tavily','tool_result':{'results':[{'url':URL,'title':'Sample','raw_content':'Tavily page text'}]}}).encode()
    assert store(tmp_path).import_web_plugin_export(raw)['direct_plugin_authentication'] is False


@pytest.mark.parametrize('payload', [
    {'provider':'tinyfish','tool_result':{'text':'{}'}},
    {'provider':'tinyfish','tool_result':{'results':[]}},
    {'provider':'tinyfish','tool_result':{'results':[{'url':'file:///etc/passwd','title':'bad','text':'evil'}]}},
    {'provider':'tinyfish','tool_result':{'results':[{'url':URL,'title':'x','text':'x'}]*11}},
    {'provider':'firecrawl','tool_result':{'data':{'markdown':'missing url'}}},
    {'provider':'tavily','tool_result':{'results':[{'url':URL,'title':'x','raw_content':'text','metadata':'invalid'}]}},
    {'provider':'fake','tool_result':{'results':[{'url':URL,'title':'x','text':'test'}]}},
])
def test_forged_or_invalid_native_envelopes_are_rejected(tmp_path,payload):
    s=store(tmp_path)
    with pytest.raises(ValueError):
        s.import_web_plugin_export(json.dumps(payload).encode())
    with sqlite3.connect(s.path) as con:
        assert con.execute('SELECT COUNT(*) FROM public_plugin_imports').fetchone()[0]==0
