"""End-to-end handoff: web plugin export -> research capture -> market review.

Uses a small PUBLIC excerpt saved from a real TinyFish read; the pipeline must
never mistake a plugin's claimed snippet for verified product-market fit.
"""
import json
import sqlite3
from pathlib import Path

from desktop.storage import LocalStore

EXCERPT_FILE=(Path(__file__).resolve().parents[1]/'docs'/'verification_public_crawling_plugin_20261015'/'tinyfish_live_excerpts.json')


def test_plugin_public_material_can_be_reviewed_for_a_business_candidate(tmp_path):
    s=LocalStore(tmp_path/'research-company.db')
    s.setup_owner('analyst','analyst-long-password')
    candidate=s.generate_business_candidates('개발자', '문서 검색 자동화',1)['created_ids'][0]
    receipt=s.import_web_plugin_export(EXCERPT_FILE.read_bytes())
    assert receipt['provider']=='tinyfish' and receipt['source_verified'] is False
    capture_id=receipt['capture_ids'][0]
    capture=s.read_offline_research(capture_id)
    excerpt=capture['body'][:min(36,len(capture['body']))]
    assert len(excerpt)>=8
    link=s.link_market_evidence(candidate,capture_id,'competition','context',excerpt,'기술 문서 예제의 주장 검토만 수행')
    assert s.review_market_evidence(link,'noted')['source_verified'] is False
    evidence=s.market_evidence_summary(candidate)
    assert evidence['categories']['competition']['reviewed_links']==1
    assert evidence['market_demand_verified'] is False
    assert evidence['competition_verified'] is False
    with sqlite3.connect(s.path) as con:
        provider=con.execute('SELECT provider,provenance FROM public_plugin_imports WHERE capture_id=?',(capture_id,)).fetchone()
    assert provider==('tinyfish','locally_imported_external_claim')
    reopened=LocalStore(s.path)
    reopened.login('analyst','analyst-long-password')
    assert reopened.market_evidence(candidate)[0]['capture_id']==capture_id
