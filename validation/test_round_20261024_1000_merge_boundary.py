"""역사 원본 대비 서로 독립적인 경계 삽입을 손실 없이 병합하는 회귀."""
from validation.merge_disjoint_text_changes import merge_disjoint_text


def test_insert_before_main_replacement_is_held():
    base = b'alpha\nbeta\ngamma\n'
    main = b'alpha\nBETA\ngamma\n'
    test = b'alpha\ninserted\nbeta\ngamma\n'
    result = merge_disjoint_text(base, main, test)
    assert result is None


def test_insert_after_main_replacement_is_held():
    base = b'alpha\nbeta\ngamma\n'
    main = b'alpha\nBETA\ngamma\n'
    test = b'alpha\nbeta\ninserted\ngamma\n'
    result = merge_disjoint_text(base, main, test)
    assert result is None


def test_insert_inside_changed_span_is_held():
    base = b'alpha\nbeta\ngamma\ndelta\n'
    main = b'alpha\nBETA-GAMMA\ndelta\n'
    test = b'alpha\nbeta\ninserted\ngamma\ndelta\n'
    assert merge_disjoint_text(base, main, test) is None


def test_same_position_independent_insertions_are_held():
    base = b'alpha\nbeta\n'
    main = b'alpha\nmain\nbeta\n'
    test = b'alpha\ntest\nbeta\n'
    assert merge_disjoint_text(base, main, test) is None


def test_disjoint_replacements_still_merge():
    base = b'alpha\nbeta\ngamma\n'
    main = b'ALPHA\nbeta\ngamma\n'
    test = b'alpha\nbeta\nGAMMA\n'
    result = merge_disjoint_text(base, main, test)
    assert result is not None
    assert result['content'] == b'ALPHA\nbeta\nGAMMA\n'


def test_overlapping_replacements_still_held():
    base = b'alpha\nbeta\ngamma\n'
    main = b'alpha\nMAIN\ngamma\n'
    test = b'alpha\nTEST\ngamma\n'
    assert merge_disjoint_text(base, main, test) is None


def test_merged_output_size_limit_is_enforced(monkeypatch):
    from validation import merge_disjoint_text_changes as module
    monkeypatch.setattr(module, '_MAX_TEXT_BYTES', 20)
    base = b'a\nb\nc\n'
    main = b'aaaaaaaaaa\nb\nc\n'
    test = b'a\nb\ncccccccccc\n'
    assert module.merge_disjoint_text(base, main, test) is None
