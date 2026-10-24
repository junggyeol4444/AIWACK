"""기존 AIWACK 3-way 스테이징에서 클래스 메서드 병합과 원본 불변 검사."""
import hashlib
from pathlib import Path
import tempfile
import unittest

try:
    from validation.stage_three_way_merge import stage_merge
except ImportError:
    from stage_three_way_merge import stage_merge

BASE = (b'class Worker:\n    def first(self):\n        return 1\n\n'
        b'    def second(self):\n        return 2\n')


class PythonMethodStageTests(unittest.TestCase):
    def _stage(self, main_data, test_data):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            historical, main, test, destination = (
                root / 'historical', root / 'main', root / 'test', root / 'merged')
            for folder, data in ((historical, BASE), (main, main_data), (test, test_data)):
                folder.mkdir()
                (folder / 'worker.py').write_bytes(data)
            audit = {
                'coverage_confirmed': True, 'distinct_original_paths': 1,
                'changed': [{'path': 'worker.py', 'original_versions': [
                    {'sha256': hashlib.sha256(BASE).hexdigest()}]}],
                'identical': [], 'missing': [], 'version_conflicts': [],
                'unsafe': [], 'baseline_paths_unseen': [],
                'baseline_paths_sha_mismatch': [],
            }
            result = stage_merge(audit, main, test, destination, historical)
            staged = (destination / 'worker.py').read_bytes()
            self.assertEqual((historical / 'worker.py').read_bytes(), BASE)
            self.assertEqual((main / 'worker.py').read_bytes(), main_data)
            self.assertEqual((test / 'worker.py').read_bytes(), test_data)
            self.assertTrue(result['main_original_preserved'])
            self.assertTrue(result['test_original_preserved'])
            self.assertFalse(result['github_main_updated'])
            return result, staged

    def test_disjoint_methods_staged(self):
        main = BASE.replace(b'return 1', b'return 11')
        test = BASE.replace(b'return 2', b'return 22')
        result, merged = self._stage(main, test)
        self.assertEqual(merged, main.replace(b'return 2', b'return 22'))
        self.assertIn('worker.py', result['merged_paths'])
        self.assertEqual(
            result['merged_divergent_evidence']['worker.py']['merge_policy'],
            'python_disjoint_class_methods_and_functions')

    def test_conflicting_method_held_and_main_preserved(self):
        main = BASE.replace(b'return 1', b'return 11')
        test = BASE.replace(b'return 1', b'return 33')
        result, staged = self._stage(main, test)
        self.assertEqual(staged, main)
        self.assertIn('worker.py', result['held_for_manual_review'])
        self.assertNotIn('worker.py', result['merged_paths'])

    def test_class_header_conflict_held_and_main_preserved(self):
        base = BASE
        main = base.replace(b'class Worker:', b'class Worker(object):').replace(
            b'return 1', b'return 11')
        test = base.replace(b'class Worker:', b'class Worker(Exception):').replace(
            b'return 2', b'return 22')
        result, staged = self._stage(main, test)
        self.assertEqual(staged, main)
        self.assertIn('worker.py', result['held_for_manual_review'])


if __name__ == '__main__':
    unittest.main()
