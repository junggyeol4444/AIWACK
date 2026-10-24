"""실제 Python 소스 병합: 원본·main·테스트 불변, 충돌 시 보류."""
import hashlib
import unittest

try:
    from validation.merge_disjoint_python_functions import (
        merge_disjoint_python_functions as merge, valid_python_bytes)
except ImportError:
    from merge_disjoint_python_functions import (
        merge_disjoint_python_functions as merge, valid_python_bytes)

BASE = b'"""original"""\nimport os\n\ndef first():\n    return 1\n\ndef second():\n    return 2\n'
MAIN = BASE.replace(b'return 1', b'return 11')
TEST = BASE.replace(b'return 2', b'return 22')


class PythonFunctionMergeTests(unittest.TestCase):
    def test_disjoint_functions(self):
        before = (BASE, MAIN, TEST)
        result = merge(BASE, MAIN, TEST)
        self.assertIsNotNone(result)
        self.assertIn(b'return 11', result['content'])
        self.assertIn(b'return 22', result['content'])
        self.assertEqual(result['sha256'], hashlib.sha256(result['content']).hexdigest())
        self.assertEqual(result['main_changed_functions'], ['first'])
        self.assertEqual(result['test_changed_functions'], ['second'])
        self.assertEqual(before, (BASE, MAIN, TEST))

    def test_same_function_conflict(self):
        self.assertIsNone(merge(BASE, MAIN, BASE.replace(b'return 1', b'return 33')))

    def test_import_change_held(self):
        self.assertIsNone(merge(BASE, MAIN, TEST.replace(b'import os', b'import sys')))

    def test_function_addition_held(self):
        self.assertIsNone(merge(BASE, MAIN, TEST + b'\ndef third():\n    return 3\n'))

    def test_function_reordering_held(self):
        self.assertIsNone(merge(BASE, MAIN, BASE.replace(
            b'def first():\n    return 1\n\ndef second():\n    return 2',
            b'def second():\n    return 2\n\ndef first():\n    return 1')))

    def test_decorator_is_part_of_function(self):
        base = b'def decorator(f):\n    return f\n\n@decorator\ndef first():\n    return 1\n\ndef second():\n    return 2\n'
        left = base.replace(b'    return 1', b'    return 11')
        right = base.replace(b'    return 2', b'    return 22')
        result = merge(base, left, right)
        self.assertIsNotNone(result)
        self.assertIn(b'@decorator\ndef first()', result['content'])

    def test_class_change_held(self):
        base = BASE + b'\nclass C:\n    x = 1\n'
        self.assertIsNone(merge(base, base.replace(b'return 1', b'return 11'),
                                base.replace(b'x = 1', b'x = 2')))

    def test_comments_outside_function_held(self):
        self.assertIsNone(merge(BASE, MAIN, TEST.replace(b'"""original"""', b'"""changed"""')))

    def test_invalid_encoding_held(self):
        self.assertIsNone(merge(BASE, MAIN, TEST + b'\xff'))

    def test_invalid_syntax_held(self):
        self.assertIsNone(merge(BASE, MAIN, TEST.replace(b'return 22', b'return (' )))

    def test_duplicate_function_name_held(self):
        base = BASE + b'\ndef first():\n    return 99\n'
        self.assertIsNone(merge(base, base.replace(b'return 1\n', b'return 11\n'),
                                base.replace(b'return 2\n', b'return 22\n')))

    def test_valid_python_checks(self):
        self.assertTrue(valid_python_bytes(BASE))
        for invalid in (b'', b'\xff', b'\x00', b'\xef\xbb\xbf' + BASE,
                        BASE.replace(b'\n', b'\r\n'), b'def broken(:\n'):
            self.assertFalse(valid_python_bytes(invalid))


if __name__ == '__main__':
    unittest.main()
