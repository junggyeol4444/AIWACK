"""실제 모델 출력 형식 검사: 입력은 fixture, GGUF 추론 실행이 아님."""
import json
import pytest
from desktop import company_wide_campaign as wide


def test_three_department_duplicate_json_key_rejected():
    departments = [(1, '개발부', 2, 3), (4, '고객지원부', 5, 6),
                   (7, '시장조사부', 8, 9)]
    rows = [dict(department=name, title='검증 업무',
                 instruction='실제 문서의 일치성과 근거를 검증한다')
            for _, name, _, _ in departments]
    raw = json.dumps(rows, ensure_ascii=False)
    assert len(wide._parse_group(raw, departments)) == 3
    bad = raw.replace('"title": "검증 업무"',
                      '"title": "검증 업무", "title": "변조된 업무"', 1)
    with pytest.raises(ValueError, match='중복'):
        wide._parse_group(bad, departments)


def test_single_department_duplicate_json_key_rejected():
    raw = ('{"department":"개발부","title":"검증 업무",'
           '"title":"변조 업무","instruction":"실제 문서의 근거를 검증한다"}')
    with pytest.raises(ValueError, match='중복'):
        wide._parse_single_chief_completion(raw, '모델 프롬프트', '개발부')
