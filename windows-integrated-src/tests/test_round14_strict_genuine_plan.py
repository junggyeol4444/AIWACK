"""14회차 실제 파서/감사 회귀: 모의 문자열, GGUF 실행 증빙 아님."""
import json
import pytest
from desktop import company_wide_campaign as wide

GROUP=[(1,'시장조사부',2,3),(2,'상품기획부',4,5),(3,'고객지원부',6,7)]

def _rows():
    return '\n'.join(f'{name}|자료 검토|{name}의 보고서를 작성하고 결과를 검증한다' for _,name,_,_ in GROUP)

def test_plain_generated_three_department_rows_still_parse():
    assert set(wide._parse_group(_rows(),GROUP))=={x[1] for x in GROUP}

def test_json_with_preamble_and_three_departments_still_parses():
    obj={'plans':[{'department':name,'title':'자료 검토',
                   'instruction':f'{name}의 보고서를 작성하고 결과를 검증한다'}
                  for _,name,_,_ in GROUP]}
    assert len(wide._parse_group('계획 초안:\n'+json.dumps(obj,ensure_ascii=False),GROUP))==3

def test_malformed_json_cannot_be_ignored_in_favor_of_valid_pipe_rows():
    raw='{"plans": [{"department": "시장조사부"\n'+_rows()
    with pytest.raises(ValueError,match='JSON'):
        wide._parse_group(raw,GROUP)

def test_complete_json_followed_by_unverified_pipe_rows_is_rejected():
    obj={'plans':[{'department':name,'title':'자료 검토',
                   'instruction':f'{name}의 보고서를 작성하고 결과를 검증한다'}
                  for _,name,_,_ in GROUP]}
    with pytest.raises(ValueError,match='JSON'):
        wide._parse_group(json.dumps(obj,ensure_ascii=False)+'\n'+_rows(),GROUP)

def test_json_unrecognized_shape_must_not_fall_back_to_pipe_rows():
    with pytest.raises(ValueError,match='JSON'):
        wide._parse_group('{"unknown":true}\n'+_rows(),GROUP)