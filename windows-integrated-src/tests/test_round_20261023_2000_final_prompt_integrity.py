"""최종보고 입력 JSON·실제 모델 호출 길이 검증: 로컬 구조 시험, 실GGUF 아님."""
import json
import pytest
from desktop.company_campaign_final_report import _bounded_verified_final_prompt


def _rows():
    return [dict(ordinal=i, department=f'부서{i%15+1}',
                 worker_result_excerpt='실제 승인 결과 인용',
                 chief_review_excerpt='총괄 검수 인용') for i in range(1, 31)]


def _payload(rows):
    return '\n'.join(json.dumps(row, ensure_ascii=False) for row in rows)


def test_valid_30_rows_still_fit_and_preserve_ordinals():
    prompt = _bounded_verified_final_prompt(_payload(_rows()), 'f'*64)
    assert len(prompt) <= 3000
    assert [json.loads(line)['n'] for line in prompt.splitlines() if line.startswith('{')] == list(range(1, 31))


def test_duplicate_json_key_rejected_without_silent_override():
    lines = _payload(_rows()).splitlines()
    lines[0] = lines[0].replace('"ordinal": 1', '"ordinal": 1, "ordinal": 1')
    with pytest.raises(ValueError, match='중복 키'):
        _bounded_verified_final_prompt('\n'.join(lines), 'f'*64)


def test_nonstandard_json_number_rejected():
    lines = _payload(_rows()).splitlines()
    lines[0] = lines[0].replace('"ordinal": 1', '"ordinal": NaN')
    with pytest.raises(ValueError, match='비표준 상수'):
        _bounded_verified_final_prompt('\n'.join(lines), 'f'*64)


def test_department_control_character_rejected():
    rows = _rows(); rows[0]['department'] = '부서\n변조'
    with pytest.raises(ValueError, match='순서·형식'):
        _bounded_verified_final_prompt(_payload(rows), 'f'*64)


def test_non_object_row_rejected():
    lines = _payload(_rows()).splitlines(); lines[0] = '[]'
    with pytest.raises(ValueError, match='순서·형식'):
        _bounded_verified_final_prompt('\n'.join(lines), 'f'*64)
