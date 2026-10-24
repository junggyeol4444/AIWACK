"""15부서 30업무 최종보고 입력의 순서·중복 검증.

합성 SQLite 비의존 데이터만 사용하며 실제 GGUF 실행 결과가 아니다.
"""
import json

import pytest

from desktop import company_campaign_final_report as final_report
from desktop.company_operations import BLUEPRINT_DEPARTMENTS


def _rows():
    return [
        {"ordinal": index, "department": department,
         "worker_result_excerpt": "직원 실제 승인 결과 원문 일부",
         "chief_review_excerpt": "총괄 실제 검수 결과 원문 일부"}
        for index, department in enumerate(
            [name for name, _ in BLUEPRINT_DEPARTMENTS for _ in range(2)], 1)
    ]


def _encode(rows):
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)


def test_final_prompt_preserves_all_fifteen_departments_and_thirty_steps():
    prompt = final_report._bounded_verified_final_prompt(_encode(_rows()), "a" * 64)
    assert len(prompt) <= 3000
    assert "전체30업무_검증원본_SHA256:" + "a" * 64 in prompt
    for name, _ in BLUEPRINT_DEPARTMENTS:
        assert prompt.count('"department":"' + name + '"') == 2


def test_final_prompt_rejects_duplicate_department_substituted_for_another():
    rows = _rows()
    rows[-1]["department"] = rows[0]["department"]
    with pytest.raises(ValueError, match="부서·순서"):
        final_report._bounded_verified_final_prompt(_encode(rows), "a" * 64)


def test_final_prompt_rejects_department_pair_reordering():
    rows = _rows()
    rows[1]["department"], rows[2]["department"] = (
        rows[2]["department"], rows[1]["department"])
    with pytest.raises(ValueError, match="부서·순서"):
        final_report._bounded_verified_final_prompt(_encode(rows), "a" * 64)


def test_final_prompt_rejects_missing_step_without_inventing_content():
    with pytest.raises(ValueError, match="순서·형식"):
        final_report._bounded_verified_final_prompt(_encode(_rows()[:-1]), "a" * 64)
