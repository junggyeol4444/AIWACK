"""기존 main·테스트·역사 원본 폴더를 건드리지 않는 Python 병합 통합 검사."""
import hashlib
from pathlib import Path
import tempfile
import unittest

try:
    from validation.stage_three_way_merge import stage_merge
except ImportError:
    from stage_three_way_merge import stage_merge

BASE = b'def first():\n    return 1\n\ndef second():\n    return 2\n'


class PythonMergeStageTests(unittest.TestCase):
    def _run_stage(self, main_data, test_data):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / 'history'
            main = root / 'main'
            test = root / 'test'
            output = root / 'merged'
            for folder, body in ((original, BASE), (main, main_data), (test, test_data)):
                folder.mkdir()
                (folder / 'app.py').write_bytes(body)
            audit = {
                'coverage_confirmed': True,
                'distinct_original_paths': 1,
                'changed': [{'path': 'app.py', 'original_versions': [
                    {'sha256': hashlib.sha256(BASE).hexdigest()}]}],
                'identical': [], 'missing': [], 'version_conflicts': [],
                'unsafe': [], 'baseline_paths_unseen': [],
                'baseline_paths_sha_mismatch': [],
            }
            result = stage_merge(audit, main, test, output, original)
            merged = (output / 'app.py').read_bytes()
            self.assertEqual((original / 'app.py').read_bytes(), BASE)
            self.assertEqual((main / 'app.py').read_bytes(), main_data)
            self.assertEqual((test / 'app.py').read_bytes(), test_data)
            self.assertTrue(result['main_original_preserved'])
            self.assertTrue(result['test_original_preserved'])
            self.assertFalse(result['github_main_updated'])
            return result, merged

    def test_disjoint_python_functions_staged(self):
        main = BASE.replace(b'return 1', b'return 11')
        test = BASE.replace(b'return 2', b'return 22')
        result, merged = self._run_stage(main, test)
        self.assertIn('app.py', result['merged_paths'])
        self.assertEqual(merged, test.replace(b'return 1', b'return 11'))
        self.assertEqual(
            result['merged_divergent_evidence']['app.py']['merge_policy'],
            'python_disjoint_top_level_functions')

    def test_same_function_conflict_stays_main(self):
        main = BASE.replace(b'return 1', b'return 11')
        test = BASE.replace(b'return 1', b'return 22')
        result, merged = self._run_stage(main, test)
        self.assertEqual(merged, main)
        self.assertIn('app.py', result['held_for_manual_review'])
        self.assertNotIn('app.py', result['merged_paths'])


if __name__ == '__main__':
    unittest.main()
