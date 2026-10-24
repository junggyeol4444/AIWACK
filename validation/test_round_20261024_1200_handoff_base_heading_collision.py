"""AIWACK 기존 인수인계 제목 재사용 충돌을 원본 보존형으로 차단한다."""
import hashlib

from validation.merge_append_only_handoffs import merge_append_only_handoffs

PATH = 'docs/AIWACK_20261023_전체누적_인수인계.md'
BASE = '# 원본\n\n## 기존 기록\n내용\n'.encode('utf-8')


def _merge(left: str, right: str):
    return merge_append_only_handoffs(
        PATH, BASE, BASE + left.encode('utf-8'), BASE + right.encode('utf-8'))


def test_existing_base_heading_cannot_be_reused():
    assert _merge('\n## 기존 기록\n재기록\n',
                  '\n## 새 기록\n정상\n') is None


def test_existing_base_heading_whitespace_alias_is_blocked():
    assert _merge('\n## 기존   기록\n중복\n',
                  '\n## 새 기록\n정상\n') is None


def test_existing_base_heading_case_alias_is_blocked():
    base = b'# original\n\n## Windows PASS\noriginal\n'
    assert merge_append_only_handoffs(
        PATH, base,
        base + b'\n## windows pass\nnot a new round\n',
        base + b'\n## other round\nvalid\n') is None


def test_disjoint_new_headings_remain_mergeable():
    left = '\n## 12시 실제 개발\n변경 1\n'.encode('utf-8')
    right = '\n## 13시 실제 개발\n변경 2\n'.encode('utf-8')
    result = merge_append_only_handoffs(PATH, BASE, BASE + left, BASE + right)
    assert result is not None
    assert result['content'] == BASE + left + right
    assert result['sha256'] == hashlib.sha256(BASE + left + right).hexdigest()


def test_new_headings_whitespace_alias_between_branches_is_blocked():
    assert _merge('\n## Same Heading\nleft\n',
                  '\n## Same   Heading\nright\n') is None


def test_stage_merge_keeps_originals_and_holds_reused_base_heading(tmp_path):
    from validation.stage_three_way_merge import stage_merge

    main, test, historical, staged = [
        tmp_path / name for name in ('main', 'test', 'history', 'staged')]
    for root in (main, test, historical):
        (root / 'docs').mkdir(parents=True)
    left = BASE + '\n## 기존 기록\n중복\n'.encode('utf-8')
    right = BASE + '\n## 새로운 회차\n독립\n'.encode('utf-8')
    (main / PATH).write_bytes(left)
    (test / PATH).write_bytes(right)
    (historical / PATH).write_bytes(BASE)
    audit = {
        'coverage_confirmed': True,
        'identical': [{'path': PATH, 'original_versions': [
            {'sha256': hashlib.sha256(BASE).hexdigest()}]}],
        'changed': [], 'missing': [], 'version_conflicts': []}
    result = stage_merge(audit, main, test, staged, historical)
    assert PATH in result['held_for_manual_review']
    assert (staged / PATH).read_bytes() == left
    assert (main / PATH).read_bytes() == left
    assert (test / PATH).read_bytes() == right
