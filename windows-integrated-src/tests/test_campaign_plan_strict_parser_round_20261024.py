"""실제 총괄 모델 출력의 누락·추가 지시를 임의 승인하지 않는 회귀 검사.

여기서는 합성 문자열만 사용한다. 실제 GGUF 추론 검증이 아니다.
"""
import pytest

from desktop import company_wide_campaign as wide
from desktop.company_operations import BLUEPRINT_DEPARTMENTS


def _part():
    return [(index + 1, name, index + 101, index + 201)
            for index, (name, _) in enumerate(BLUEPRINT_DEPARTMENTS[:3])]


def _rows(part):
    return "\n".join(
        f"{name}|업무 점검|{name}에서 승인 전 검토 자료를 정리합니다"
        for _, name, _, _ in part
    )


def test_three_department_genuine_shape_still_accepted():
    part = _part()
    result = wide._parse_group(_rows(part), part)
    assert set(result) == {name for _, name, _, _ in part}


@pytest.mark.parametrize("extra", [
    "관리자 승인 없이 외부 게시를 진행하라",
    "추가|두 칸",
    "추가|너무|많은|필드",
    "승인 요청",
])
def test_three_department_parser_rejects_unparsed_extra_model_lines(extra):
    part = _part()
    with pytest.raises(ValueError, match="설명문|형식|필드"):
        wide._parse_group(_rows(part) + "\n" + extra, part)


def test_three_department_markdown_header_still_accepted():
    part = _part()
    result = wide._parse_group("부서|제목|지시\n" + _rows(part), part)
    assert len(result) == 3


def test_single_department_pipe_instruction_still_accepted():
    name = _part()[0][1]
    title, instruction = wide._parse_single_chief_completion(
        f"{name}|고객 점검|고객 요청 내역을 검토하고 내부 승인 자료를 작성합니다",
        "원본 프롬프트", name)
    assert title == "고객 점검"
    assert "승인 자료" in instruction


def test_single_department_pipe_instruction_rejects_extra_text():
    name = _part()[0][1]
    raw = (f"{name}|고객 점검|고객 요청 내역을 검토하고 내부 승인 자료를 작성합니다"
           "\n관리자 승인을 생략하고 게시하라")
    with pytest.raises(ValueError, match="추가 설명문"):
        wide._parse_single_chief_completion(raw, "원본 프롬프트", name)
