"""인계 지문 변조·오래된 승인 원본 재검사: 모의 스냅샷만 사용."""
from __future__ import annotations

import hashlib
import json

import pytest

from desktop import company_campaign_chain_integrity as chain


def _receipt(campaign_id=4, report_id=30):
    data = {
        'format': 'AIWACK_LOCAL_GENUINE_CAMPAIGN_CHAIN_V1',
        'campaign_id': campaign_id,
        'chief_final_report_id': report_id,
        'owner_approved_dossier_id': 55,
        'independent_gguf_binary_verified': False,
        'physical_windows_10_11_gui_verified': False,
        'final_T01_T20_acceptance_passed': False,
    }
    digest = hashlib.sha256(json.dumps(
        data, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()
    return {**data, 'receipt_sha256': digest}


def test_identical_receipt_is_read_only_and_not_independent_gguf(monkeypatch):
    original = _receipt()
    monkeypatch.setattr(chain, 'snapshot', lambda store, campaign_id: original)
    verified = chain.verify_receipt(object(), 4, dict(original))
    assert verified['verified'] is True
    assert verified['read_only'] is True
    assert verified['independent_gguf_binary_verified'] is False
    assert verified['physical_windows_10_11_gui_verified'] is False


def test_modified_receipt_fails_even_with_original_digest(monkeypatch):
    original = _receipt()
    monkeypatch.setattr(chain, 'snapshot', lambda store, campaign_id: original)
    tampered = dict(original, chief_final_report_id=999)
    with pytest.raises(ValueError, match='변경'):
        chain.verify_receipt(object(), 4, tampered)


def test_old_receipt_fails_when_owner_original_changes(monkeypatch):
    original = _receipt()
    latest = _receipt(report_id=31)
    monkeypatch.setattr(chain, 'snapshot', lambda store, campaign_id: latest)
    with pytest.raises(ValueError, match='현재 승인 원본'):
        chain.verify_receipt(object(), 4, original)


def test_recomputed_tampered_receipt_still_fails_against_current_original(monkeypatch):
    original = _receipt()
    forged = _receipt(report_id=999)
    monkeypatch.setattr(chain, 'snapshot', lambda store, campaign_id: original)
    with pytest.raises(ValueError, match='현재 승인 원본'):
        chain.verify_receipt(object(), 4, forged)


@pytest.mark.parametrize('invalid', [None, [], {}, {'receipt_sha256': 'x'}])
def test_missing_or_invalid_receipt_fails_closed(monkeypatch, invalid):
    original = _receipt()
    monkeypatch.setattr(chain, 'snapshot', lambda store, campaign_id: original)
    with pytest.raises(ValueError):
        chain.verify_receipt(object(), 4, invalid)


@pytest.mark.parametrize('invalid_id', [True, 0, -1, '4'])
def test_invalid_campaign_id_rejected_before_snapshot(invalid_id):
    with pytest.raises(ValueError, match='양의 정수'):
        chain.verify_receipt(object(), invalid_id, _receipt())


def test_cross_campaign_receipt_rejected_without_source_query(monkeypatch):
    def must_not_read(*args, **kwargs):
        raise AssertionError('다른 캠페인 원본을 조회해서는 안 됩니다')
    monkeypatch.setattr(chain, 'snapshot', must_not_read)
    with pytest.raises(ValueError, match='캠페인 번호'):
        chain.verify_receipt(object(), 5, _receipt(campaign_id=4))


@pytest.mark.parametrize('invalid', [True, 4.0, '4', None])
def test_receipt_campaign_identifier_must_be_exact_integer(monkeypatch, invalid):
    monkeypatch.setattr(chain, 'snapshot', lambda *args: _receipt())
    receipt = _receipt()
    receipt['campaign_id'] = invalid
    with pytest.raises(ValueError, match='캠페인 번호'):
        chain.verify_receipt(object(), 4, receipt)


def test_receipt_json_rejects_unpaired_surrogate_as_value_error():
    raw = '{"invalid":"' + chr(0xD800) + '"}'
    with pytest.raises(ValueError, match='유니코드'):
        chain.verify_receipt_json(object(), 4, raw)


def test_receipt_digest_rejects_uppercase_sha256(monkeypatch):
    original = _receipt()
    monkeypatch.setattr(chain, 'snapshot', lambda store, campaign_id: original)
    forged = dict(original, receipt_sha256='A' * 64)
    with pytest.raises(ValueError, match='SHA256'):
        chain.verify_receipt(object(), 4, forged)
