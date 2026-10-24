"""총괄 실모델 출력·승인 원본 증빙 결합 회귀.

합성 데이터 테스트이며 Windows GUI/실제 GGUF 실행 결과를 대신하지 않는다.
"""
import json

import pytest

from desktop import company_campaign_final_report as final_report
from desktop import company_wide_campaign as campaign
from desktop.company_operations import BLUEPRINT_DEPARTMENTS


def _group():
    return [(i + 1, name, i + 101, i + 201)
            for i, (name, _) in enumerate(BLUEPRINT_DEPARTMENTS[:3])]


def _plans(group):
    return [{"department": name, "title": "검토 업무",
             "instruction": "승인 자료를 확인하고 검토 결과를 작성합니다"}
            for _, name, _, _ in group]


def _rows():
    return [
        {"ordinal": i, "department": name, "artifact_id": i,
         "artifact_sha256": "a" * 64, "chief_report_sha256": "b" * 64,
         "worker_result_excerpt": "승인된 직원 결과", "chief_review_excerpt": "총괄 검수 결과"}
        for i, name in enumerate(
            [name for name, _ in BLUEPRINT_DEPARTMENTS for _ in range(2)], 1)
    ]


def _prompt(rows):
    return final_report._bounded_verified_final_prompt(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows), "c" * 64)


def test_single_json_plan_is_accepted():
    group = _group()
    assert len(campaign._parse_group(json.dumps(_plans(group), ensure_ascii=False), group)) == 3


def test_two_json_objects_cannot_discard_first_one():
    group = _group()
    first = json.dumps({"unexpected": "discard me"}, ensure_ascii=False)
    second = json.dumps(_plans(group), ensure_ascii=False)
    with pytest.raises(ValueError, match="추가 출력|손상"):
        campaign._parse_group(first + "\n" + second, group)


def test_two_valid_json_plans_cannot_be_silently_collapsed():
    group = _group()
    raw = json.dumps(_plans(group), ensure_ascii=False)
    with pytest.raises(ValueError, match="추가 출력"):
        campaign._parse_group(raw + "\n" + raw, group)


def test_single_department_legacy_json_rejects_extra_instruction_field():
    name = _group()[0][1]
    raw = json.dumps({"department": name, "title": "검토 업무",
                      "instruction": "고객 현황을 확인하고 승인 자료를 작성합니다",
                      "skip_approval": True}, ensure_ascii=False)
    with pytest.raises(ValueError, match="요청하지 않은 필드"):
        campaign._parse_single_real_chief(raw, name, "원본 요청")


def test_single_department_legacy_json_still_accepts_original_fields():
    name = _group()[0][1]
    raw = json.dumps({"department": name, "title": "검토 업무",
                      "instruction": "고객 현황을 확인하고 승인 자료를 작성합니다"}, ensure_ascii=False)
    assert campaign._parse_single_real_chief(raw, name, "원본 요청")[0] == "검토 업무"


def test_final_report_proofed_thirty_steps_still_fit_prompt():
    prompt = _prompt(_rows())
    assert len(prompt) <= 3000
    assert prompt.count('"department":') == 30


def test_final_report_rejects_reused_artifact_id():
    rows = _rows()
    rows[-1]["artifact_id"] = rows[0]["artifact_id"]
    with pytest.raises(ValueError, match="증빙 식별자"):
        _prompt(rows)


def test_final_report_rejects_partial_proof_metadata():
    rows = _rows()
    del rows[-1]["chief_report_sha256"]
    with pytest.raises(ValueError, match="증빙 필드"):
        _prompt(rows)


@pytest.mark.parametrize("invalid", ["A" * 64, "0" * 63, "z" * 64, None])
def test_final_report_rejects_invalid_source_sha256(invalid):
    rows = _rows()
    rows[7]["artifact_sha256"] = invalid
    with pytest.raises(ValueError, match="증빙 식별자"):
        _prompt(rows)


def test_final_report_rejects_bool_artifact_id():
    rows = _rows()
    rows[0]["artifact_id"] = True
    with pytest.raises(ValueError, match="증빙 식별자"):
        _prompt(rows)
