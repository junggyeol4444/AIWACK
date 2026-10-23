"""GGUF 실제 모델 출력의 JSON 충돌을 허용하지 않는 fixture 회귀(실추론 아님)."""
import json
import pytest
from desktop import company_wide_campaign as wide


DEPTS = [(1, '개발부', 2, 3), (4, '고객지원부', 5, 6), (7, '시장조사부', 8, 9)]


def rows():
    return [{'department': name, 'title': '검증 업무',
             'instruction': '원본 근거와 승인 증빙을 비교 검증한다'}
            for _, name, _, _ in DEPTS]


@pytest.mark.parametrize('token', ['NaN', 'Infinity', '-Infinity'])
def test_group_nonstandard_numeric_rejected(token):
    bad = json.dumps({'departments': rows()}, ensure_ascii=False).replace(
        '"title": "검증 업무"', '"title": '+token, 1)
    with pytest.raises(ValueError, match='비표준 숫자'):
        wide._parse_group(bad, DEPTS)


@pytest.mark.parametrize('token', ['NaN', 'Infinity', '-Infinity'])
def test_single_nonstandard_numeric_rejected(token):
    bad = ('{"department":"개발부","title":'+token+
           ',"instruction":"원본 근거와 승인 증빙을 비교 검증한다"}')
    with pytest.raises(ValueError, match='비표준 숫자'):
        wide._parse_single_chief_completion(bad, '프롬프트', '개발부')


def test_group_wrapper_alias_conflict_rejected():
    payload = {'departments': rows(), 'plans': rows()[:-1]}
    with pytest.raises(ValueError, match='별칭 충돌'):
        wide._parse_group(json.dumps(payload, ensure_ascii=False), DEPTS)


def test_group_single_wrapper_valid():
    assert len(wide._parse_group(json.dumps({'departments': rows()}, ensure_ascii=False), DEPTS)) == 3


def test_single_valid_json_preserved():
    raw = json.dumps(rows()[0], ensure_ascii=False)
    assert wide._parse_single_chief_completion(raw, '프롬프트', '개발부')[0] == '검증 업무'
