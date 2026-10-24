"""기존 3-way 병합에서 서로 다른 최상위 클래스 변경의 원본 보존 검증."""
import hashlib
from pathlib import Path
import tempfile
import unittest

try:
    from validation.stage_three_way_merge import stage_merge
except ImportError:
    from stage_three_way_merge import stage_merge

BASE = (b'import os\n\nclass A:\n    value = 1\n\n'
        b'class B:\n    value = 2\n\n'
        b'def report():\n    return "ok"\n')


class PythonBlocksStageTests(unittest.TestCase):
    def _stage(self, main_data, test_data):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            history, main, test, destination = (
                root / 'historical', root / 'main', root / 'test', root / 'merged')
            for folder, body in ((history, BASE), (main, main_data), (test, test_data)):
                folder.mkdir()
                (folder / 'company.py').write_bytes(body)
            audit = {
                'coverage_confirmed': True, 'distinct_original_paths': 1,
                'changed': [{'path': 'company.py', 'original_versions': [
                    {'sha256': hashlib.sha256(BASE).hexdigest()}]}],
                'identical': [], 'missing': [], 'version_conflicts': [],
                'unsafe': [], 'baseline_paths_unseen': [],
                'baseline_paths_sha_mismatch': [],
            }
            result = stage_merge(audit, main, test, destination, history)
            staged = (destination / 'company.py').read_bytes()
            self.assertEqual((history / 'company.py').read_bytes(), BASE)
            self.assertEqual((main / 'company.py').read_bytes(), main_data)
            self.assertEqual((test / 'company.py').read_bytes(), test_data)
            self.assertFalse(result['github_main_updated'])
            return result, staged

    def test_disjoint_classes_staged(self):
        main = BASE.replace(b'value = 1', b'value = 11')
        test = BASE.replace(b'value = 2', b'value = 22')
        result, staged = self._stage(main, test)
        self.assertEqual(staged, main.replace(b'value = 2', b'value = 22'))
        self.assertEqual(result['merged_divergent_evidence']['company.py']['merge_policy'],
                         'python_disjoint_top_level_classes_and_functions')

    def test_same_class_conflict_held(self):
        main = BASE.replace(b'value = 1', b'value = 11')
        test = BASE.replace(b'value = 1', b'value = 33')
        result, staged = self._stage(main, test)
        self.assertEqual(staged, main)
        self.assertIn('company.py', result['held_for_manual_review'])

    def test_independent_class_and_function(self):
        main = BASE.replace(b'value = 1', b'value = 11')
        test = BASE.replace(b'"ok"', b'"changed"')
        result, staged = self._stage(main, test)
        self.assertEqual(staged, main.replace(b'"ok"', b'"changed"'))
        self.assertIn('company.py', result['merged_paths'])


if __name__ == '__main__':
    unittest.main()
