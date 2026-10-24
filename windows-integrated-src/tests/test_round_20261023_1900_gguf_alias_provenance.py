"""Genuine GGUF chief JSON alias integrity: fixture-only regression."""
import json
import pytest
from desktop import company_wide_campaign as wide


def _group():
    return [(1, '개발부', 2, 3), (4, '고객지원부', 5, 6),
            (7, '시장조사부', 8, 9)]


def test_three_department_conflicting_alias_rejected():
    rows = [dict(department=name, title='검증 업무',
                 instruction='원본 근거와 승인 증빙을 비교 검증한다')
            for _, name, _, _ in _group()]
    rows[0]['부서명'] = '다른부서'
    with pytest.raises(ValueError, match='별칭 충돌'):
        wide._parse_group(json.dumps(rows, ensure_ascii=False), _group())


def test_single_department_conflicting_title_rejected():
    raw = json.dumps(dict(department='개발부', title='검증 업무',
                          제목='변조 업무', instruction='원본 근거와 승인 증빙을 비교 검증한다'),
                     ensure_ascii=False)
    with pytest.raises(ValueError, match='별칭 충돌'):
        wide._parse_single_chief_completion(raw, '모델 프롬프트', '개발부')


def test_single_department_matching_alias_accepted():
    raw = json.dumps(dict(department='개발부', 부서명='개발부',
                          title='검증 업무', 제목='검증 업무',
                          instruction='원본 근거와 승인 증빙을 비교 검증한다'),
                     ensure_ascii=False)
    title, instruction = wide._parse_single_chief_completion(raw, '모델 프롬프트', '개발부')
    assert title == '검증 업무' and '원본 근거' in instruction


def test_old_single_real_parser_rejects_conflicting_alias():
    raw = json.dumps(dict(department='개발부', 부서명='다른부서',
                          title='검증 업무', instruction='원본 근거와 승인 증빙을 비교 검증한다'),
                     ensure_ascii=False)
    with pytest.raises(ValueError, match='별칭 충돌'):
        wide._parse_single_real_chief(raw, '개발부', '모델 프롬프트')
