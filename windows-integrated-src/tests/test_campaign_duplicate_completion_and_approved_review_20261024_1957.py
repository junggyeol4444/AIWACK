"""기존 GGUF 총괄 출력 및 승인 원문 보존 개발 회귀.

합성 SQLite 조회 결과를 사용하며 실 GGUF/Windows EXE 검증은 아님.
"""
import hashlib

import pytest

from desktop import company_campaign_final_report as final_report
from desktop import company_wide_campaign as campaign


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params):
        assert "company_chief_task_reports" in query
        assert params == (11, 22)
        return _Cursor(self.rows)


class _Store:
    def __init__(self, rows):
        self.rows = rows

    def _connect(self):
        return _Connection(self.rows)


def _payload():
    worker = "승인된 직원의 실제 결과"
    review = "총괄 AI의 승인 검수 기록"
    whash = hashlib.sha256(worker.encode("utf-8")).hexdigest()
    rhash = hashlib.sha256(review.encode("utf-8")).hexdigest()
    return {
        "steps": [{
            "ordinal": 1, "department": "기획",
            "artifact_id": 11, "task_id": 22,
            "artifact_sha256": whash, "chief_report_sha256": rhash,
        }]
    }, (worker, review, whash, rhash)


def test_approved_review_exactly_one_match_is_kept():
    payload, row = _payload()
    text = final_report._approved_content_excerpts(_Store([row]), payload)
    assert "기획" in text
    assert row[2] in text and row[3] in text


@pytest.mark.parametrize("rows_count", [0, 2, 3])
def test_approved_review_missing_or_duplicate_is_rejected(rows_count):
    payload, row = _payload()
    with pytest.raises(ValueError, match="없거나 중복"):
        final_report._approved_content_excerpts(_Store([row] * rows_count), payload)


@pytest.mark.parametrize("index,wrong", [(0, None), (1, b"bytes"), (2, "0" * 64), (3, "f" * 64)])
def test_approved_review_invalid_text_or_digest_is_rejected(index, wrong):
    payload, row = _payload()
    broken = list(row)
    broken[index] = wrong
    with pytest.raises(ValueError, match="변경"):
        final_report._approved_content_excerpts(_Store([tuple(broken)]), payload)


def test_single_response_marker_preserves_model_completion():
    assert campaign._generated_chief_lines("RESPONSE:\n실제 부서 업무") == ["실제 부서 업무"]


def test_echoed_prompt_before_single_response_is_removed():
    prompt = "이 부서의 업무를 작성하세요"
    assert campaign._generated_chief_lines(
        prompt + "\nRESPONSE:\n승인된 모델의 부서 업무", prompt
    ) == ["승인된 모델의 부서 업무"]


@pytest.mark.parametrize("raw", [
    "RESPONSE: 이전 응답\nRESPONSE: 이후 응답",
    "RESPONSE: 이전 응답\n다른 내용\nRESPONSE: 이후 응답",
])
def test_multiple_response_markers_never_discard_first_output(raw):
    with pytest.raises(ValueError, match="중복된 RESPONSE"):
        campaign._generated_chief_lines(raw)


def test_duplicate_response_marker_is_rejected_in_single_chief_parser():
    with pytest.raises(ValueError, match="중복된 RESPONSE"):
        campaign._parse_single_chief_completion(
            "RESPONSE: 첫 번째 계획\nRESPONSE: 두 번째 계획",
            "부서 계획 요청", "기획",
        )
