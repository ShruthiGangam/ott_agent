import tempfile
import unittest
from pathlib import Path
from tools.package_submission import members, package, safe_member


class PackagingTests(unittest.TestCase):
    def test_private_files_are_excluded_and_evaluator_assets_retained(self):
        for relative in ('.env', 'submission/.env', '.venv/x.py', 'submission/runs/x.json',
                         'submission/.llm_response_cache_v2.json', 'submission/state.sqlite',
                         'submission/__pycache__/a.pyc', 'submission/example.egg-info/SOURCES.txt'):
            self.assertFalse(safe_member(Path(relative)), relative)
        selected = members(Path(__file__).resolve().parents[2])
        self.assertIn('submission/ott_agent/assets/recorded_responses.jsonl', selected)
        self.assertIn('submission/sample_replay/decisions.jsonl', selected)
        self.assertIn('submission/.env.example', selected)
        self.assertTrue(all(safe_member(Path(name)) for name in selected))

    def test_packager_refuses_existing_deliverable(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)/'existing.zip'
            target.write_bytes(b'keep')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                package(Path(__file__).resolve().parents[2], target)
            self.assertEqual(target.read_bytes(), b'keep')
