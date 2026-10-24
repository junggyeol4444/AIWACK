"""AIWACK 인수인계 원문 보존형 추가 기록 병합 회귀."""
import hashlib
from validation.merge_append_only_handoffs import merge_append_only_handoffs as merge

PATH = 'docs/AIWACK_20261023_전체누적_인수인계.md'
BASE = '# 원본 인수인계\n\n## 기존\n기록\n'.encode()
LEFT = '\n## 11시 main 개발\nmain 기록\n'.encode()
RIGHT = '\n## 12시 test 개발\ntest 기록\n'.encode()


def test_disjoint_append_sections_preserve_every_byte():
    result = merge(PATH, BASE, BASE + LEFT, BASE + RIGHT)
    assert result['content'] == BASE + LEFT + RIGHT
    assert result['sha256'] == hashlib.sha256(result['content']).hexdigest()
    assert result['main_appended_bytes'] == len(LEFT)
    assert result['test_appended_bytes'] == len(RIGHT)


def test_prefix_edit_must_not_merge():
    assert merge(PATH, BASE, b'X' + BASE + LEFT, BASE + RIGHT) is None


def test_same_section_heading_is_conflict():
    assert merge(PATH, BASE, BASE + LEFT, BASE + LEFT.replace('main 기록'.encode(), 'else 기록'.encode())) is None


def test_identical_appends_are_not_duplicated():
    assert merge(PATH, BASE, BASE + LEFT, BASE + LEFT)['content'] == BASE + LEFT


def test_shorter_append_already_in_longer_is_not_duplicated():
    extra = '\n## 13시 추가\n내용\n'.encode()
    assert merge(PATH, BASE, BASE + LEFT, BASE + LEFT + extra)['content'] == BASE + LEFT + extra


def test_non_handoff_path_not_eligible():
    assert merge('windows-integrated-src/desktop/app.py', BASE, BASE + LEFT, BASE + RIGHT) is None
    assert merge('docs/../secret.md', BASE, BASE + LEFT, BASE + RIGHT) is None


def test_no_valid_section_is_held():
    assert merge(PATH, BASE, BASE + b'just words\n', BASE + RIGHT) is None


def test_binary_or_invalid_utf8_is_held():
    assert merge(PATH, BASE, BASE + b'\x00' + LEFT, BASE + RIGHT) is None
    assert merge(PATH, BASE, BASE + b'\xff' + LEFT, BASE + RIGHT) is None


def test_oversize_is_held():
    assert merge(PATH, BASE, BASE + LEFT + b'x' * (2 * 1024 * 1024), BASE + RIGHT) is None


def test_base_without_line_boundary_is_held():
    assert merge(PATH, b'base', b'base' + LEFT, b'base' + RIGHT) is None


def test_duplicated_headings_in_one_append_are_held():
    assert merge(PATH, BASE, BASE + LEFT + LEFT, BASE + RIGHT) is None


def test_stage_merge_real_handoff_append_preserves_main_and_test(tmp_path):
    from validation.stage_three_way_merge import stage_merge
    main, test, historical, staged = [tmp_path / n for n in ('main', 'test', 'history', 'staged')]
    for p in (main, test, historical):
        (p / 'docs').mkdir(parents=True)
    for folder, body in ((main, BASE + LEFT), (test, BASE + RIGHT), (historical, BASE)):
        (folder / PATH).write_bytes(body)
    audit = {'coverage_confirmed': True, 'identical': [
        {'path': PATH, 'original_versions': [{'sha256': hashlib.sha256(BASE).hexdigest()}]}],
        'changed': [], 'missing': [], 'version_conflicts': []}
    result = stage_merge(audit, main, test, staged, historical)
    assert (staged / PATH).read_bytes() == BASE + LEFT + RIGHT
    assert (main / PATH).read_bytes() == BASE + LEFT
    assert (test / PATH).read_bytes() == BASE + RIGHT
    assert result['merged_divergent_evidence'][PATH]['merge_policy'] == 'append_only_distinct_sections'
