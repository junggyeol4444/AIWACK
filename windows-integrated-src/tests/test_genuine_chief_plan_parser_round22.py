"""Genuine chief output parsing regression, not a GGUF inference acceptance test."""
import json

import pytest

from desktop.company_wide_campaign import _parse_group


GROUP = [
    (1, "기획부", 2, 3),
    (2, "개발부", 4, 5),
    (3, "디자인부", 6, 7),
]
ROWS = [
    ("기획부", "시장 조사", "잠재 고객의 요구사항과 경쟁사의 제품을 조사하세요"),
    ("개발부", "설계 검증", "기술 요구사항을 검토하고 구현 계획을 제출하세요"),
    ("디자인부", "사용자 화면", "사용자 화면의 접근성 개선안을 제안하세요"),
]


def test_genuine_pipe_rows():
    output = "\n".join("|".join(row) for row in ROWS)
    assert set(_parse_group(output, GROUP)) == {"기획부", "개발부", "디자인부"}


def test_genuine_markdown_list_and_fullwidth_separator():
    output = "\n".join(f"{i}. {name}｜{title}｜{instruction}" for i, (name, title, instruction) in enumerate(ROWS, 1))
    assert _parse_group(output, GROUP)["기획부"][0] == "시장 조사"


def test_genuine_json_plan():
    output = json.dumps({"departments": [
        {"department": name, "title": title, "instruction": instruction}
        for name, title, instruction in ROWS
    ]}, ensure_ascii=False)
    assert len(_parse_group(output, GROUP)) == 3


def test_reject_unknown_department_even_if_valid_three():
    output = "\n".join("|".join(row) for row in ROWS)
    with pytest.raises(ValueError):
        _parse_group(output + "\n재무부|실행|허가되지 않은 부서 업무", GROUP)


def test_reject_missing_and_duplicate():
    with pytest.raises(ValueError):
        _parse_group("\n".join("|".join(row) for row in ROWS[:2]), GROUP)
    output = "\n".join("|".join(row) for row in ROWS)
    with pytest.raises(ValueError):
        _parse_group(output + "\n" + "|".join(ROWS[0]), GROUP)


def test_reject_malformed_json_even_if_pipe_follows():
    output = '{"departments": [\n' + "\n".join("|".join(row) for row in ROWS)
    with pytest.raises(ValueError):
        _parse_group(output, GROUP)


def test_reject_echo_without_real_plan():
    with pytest.raises(ValueError):
        _parse_group("담당 부서: 기획부, 개발부, 디자인부\n부서명|작업 제목|작업 지시", GROUP)


def test_single_chief_pipe_output_is_real_text():
    from desktop.company_wide_campaign import _parse_single_real_chief
    title, instruction = _parse_single_real_chief(
        "기획부|시장 조사|잠재 고객의 요구사항과 경쟁사의 제품을 조사하세요",
        "기획부", "요청 프롬프트")
    assert title == "시장 조사"
    assert "요구사항" in instruction


def test_single_chief_refuses_wrong_department():
    from desktop.company_wide_campaign import _parse_single_real_chief
    with pytest.raises(ValueError):
        _parse_single_real_chief(
            "개발부|설계|기획부와 상관없는 개발 업무를 진행하세요",
            "기획부", "요청 프롬프트")


def test_single_chief_real_json_and_no_prompt_echo():
    from desktop.company_wide_campaign import _parse_single_real_chief
    value = '{"department":"기획부","title":"고객 분석","instruction":"고객별 수요를 조사하고 운영안을 제출하세요"}'
    assert _parse_single_real_chief(value,"기획부","요청 프롬프트")[0] == "고객 분석"
    with pytest.raises(ValueError):
        _parse_single_real_chief("요청 프롬프트","기획부","요청 프롬프트")
