"""원본 보존형 Python 최상위 블록 병합: 상충 변경은 자동 선택 금지."""
import hashlib
import unittest
from validation.merge_disjoint_python_blocks import merge_disjoint_python_blocks as merge

BASE = (b'import os\n\nclass A:\n    value = 1\n\n'
        b'class B:\n    value = 2\n\n'
        b'def report():\n    return "ok"\n')
MAIN = BASE.replace(b'value = 1', b'value = 11')
TEST = BASE.replace(b'value = 2', b'value = 22')


class PythonBlockMergeTests(unittest.TestCase):
    def test_two_classes(self):
        result = merge(BASE, MAIN, TEST)
        self.assertIsNotNone(result)
        self.assertEqual(result['content'], MAIN.replace(b'value = 2', b'value = 22'))
        self.assertEqual(result['main_changed_blocks'], ['A'])
        self.assertEqual(result['test_changed_blocks'], ['B'])
        self.assertEqual(result['sha256'], hashlib.sha256(result['content']).hexdigest())

    def test_class_and_function(self):
        result = merge(BASE, MAIN, BASE.replace(b'"ok"', b'"changed"'))
        self.assertEqual(result['test_changed_blocks'], ['report'])

    def test_function_and_class(self):
        result = merge(BASE, BASE.replace(b'"ok"', b'"changed"'), TEST)
        self.assertEqual(result['main_changed_blocks'], ['report'])

    def test_same_class_conflict(self):
        self.assertIsNone(merge(BASE, MAIN, BASE.replace(b'value = 1', b'value = 33')))

    def test_identical_class_change_not_enough(self):
        self.assertIsNone(merge(BASE, MAIN, MAIN))

    def test_import_change(self):
        self.assertIsNone(merge(BASE, MAIN, TEST.replace(b'import os', b'import sys')))

    def test_class_added(self):
        self.assertIsNone(merge(BASE, MAIN, TEST+b'\nclass C:\n    pass\n'))

    def test_class_removed(self):
        self.assertIsNone(merge(BASE, MAIN, TEST.replace(b'class B:\n    value = 22\n\n', b'')))

    def test_class_reordered(self):
        a=b'class A:\n    value = 1\n\n'
        b=b'class B:\n    value = 2\n\n'
        self.assertIsNone(merge(BASE, MAIN, BASE.replace(a+b,b+a)))

    def test_duplicate_name(self):
        dup=BASE+b'\nclass A:\n    pass\n'
        self.assertIsNone(merge(dup, dup.replace(b'value = 1', b'value = 11'),
                                dup.replace(b'value = 2', b'value = 22')))

    def test_invalid_python(self):
        self.assertIsNone(merge(BASE, MAIN, TEST.replace(b'value = 22', b'value = (')))

    def test_non_bytes(self):
        self.assertIsNone(merge(BASE.decode(), MAIN, TEST))

    def test_decorated_class(self):
        base=BASE.replace(b'class A:', b'@decorator\nclass A:')
        self.assertIsNotNone(merge(base,base.replace(b'value = 1', b'value = 11'),
                                   base.replace(b'value = 2', b'value = 22')))

    def test_outside_comment_change(self):
        self.assertIsNone(merge(BASE, MAIN, TEST.replace(b'import os', b'import os\n# extra')))

    def test_originals_unchanged(self):
        original=(BASE,MAIN,TEST)
        merge(*original)
        self.assertEqual(original,(BASE,MAIN,TEST))


if __name__ == '__main__':
    unittest.main()
