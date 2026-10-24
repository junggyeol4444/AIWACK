"""AIWACK Python 클래스 메서드 병합: 독립 변경만 허용하고 충돌은 보류."""
import hashlib
import unittest

try:
    from validation.merge_disjoint_python_methods import merge_disjoint_python_methods as merge
except ImportError:
    from merge_disjoint_python_methods import merge_disjoint_python_methods as merge

BASE = (b'import os\n\nclass Worker:\n    mode = 1\n\n'
        b'    def first(self):\n        return 1\n\n'
        b'    def second(self):\n        return 2\n')
MAIN = BASE.replace(b'return 1', b'return 11')
TEST = BASE.replace(b'return 2', b'return 22')


class PythonMethodMergeTests(unittest.TestCase):
    def test_disjoint_methods_in_one_class(self):
        originals = BASE, MAIN, TEST
        result = merge(*originals)
        self.assertIsNotNone(result)
        self.assertEqual(result['content'], MAIN.replace(b'return 2', b'return 22'))
        self.assertEqual(result['main_changed_functions'], ['Worker.first'])
        self.assertEqual(result['test_changed_functions'], ['Worker.second'])
        self.assertEqual(result['sha256'], hashlib.sha256(result['content']).hexdigest())
        self.assertEqual(originals, (BASE, MAIN, TEST))

    def test_different_classes(self):
        base = BASE + b'\nclass Other:\n    def third(self):\n        return 3\n'
        self.assertIsNotNone(merge(base, base.replace(b'return 1', b'return 11'),
                                   base.replace(b'return 3', b'return 33')))

    def test_method_and_top_level_function(self):
        base = BASE + b'\ndef top():\n    return 3\n'
        result = merge(base, base.replace(b'return 1', b'return 11'),
                       base.replace(b'return 3', b'return 33'))
        self.assertIsNotNone(result)
        self.assertEqual(result['test_changed_functions'], ['top'])

    def test_same_method_conflict(self):
        self.assertIsNone(merge(BASE, MAIN, BASE.replace(b'return 1', b'return 33')))

    def test_method_addition_held(self):
        self.assertIsNone(merge(BASE, MAIN, TEST + b'\n    def new(self):\n        return 4\n'))

    def test_class_header_change_held(self):
        self.assertIsNone(merge(BASE, MAIN, TEST.replace(b'class Worker:', b'class Worker(object):')))

    def test_class_variable_change_held(self):
        self.assertIsNone(merge(BASE, MAIN, TEST.replace(b'mode = 1', b'mode = 2')))

    def test_import_change_held(self):
        self.assertIsNone(merge(BASE, MAIN, TEST.replace(b'import os', b'import sys')))

    def test_method_reorder_held(self):
        one = b'    def first(self):\n        return 1\n\n'
        two = b'    def second(self):\n        return 2\n'
        self.assertIsNone(merge(BASE, MAIN, BASE.replace(one + two, two + b'\n' + one)))

    def test_duplicate_method_held(self):
        base = BASE + b'\n    def first(self):\n        return 99\n'
        self.assertIsNone(merge(base, base.replace(b'return 1', b'return 11'),
                                base.replace(b'return 2', b'return 22')))

    def test_duplicate_class_held(self):
        base = BASE + b'\nclass Worker:\n    def third(self):\n        return 3\n'
        self.assertIsNone(merge(base, base.replace(b'return 1', b'return 11'),
                                base.replace(b'return 2', b'return 22')))

    def test_decorated_method(self):
        base = BASE.replace(b'    def first(self):', b'    @staticmethod\n    def first(self):')
        self.assertIsNotNone(merge(base, base.replace(b'return 1', b'return 11'),
                                   base.replace(b'return 2', b'return 22')))

    def test_class_decorator_change_held(self):
        base = b'@decorator\n' + BASE
        self.assertIsNone(merge(base, base.replace(b'return 1', b'return 11'),
                                base.replace(b'@decorator', b'@other').replace(b'return 2', b'return 22')))

    def test_bad_syntax_held(self):
        self.assertIsNone(merge(BASE, MAIN, TEST.replace(b'return 22', b'return (')))

    def test_bad_encoding_held(self):
        self.assertIsNone(merge(BASE, MAIN, TEST + b'\xff'))

    def test_only_one_side_changed_held(self):
        self.assertIsNone(merge(BASE, MAIN, BASE))


if __name__ == '__main__':
    unittest.main()
