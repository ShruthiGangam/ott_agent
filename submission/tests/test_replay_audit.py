import unittest
import tempfile
from pathlib import Path
from ott_agent.audit import audit
ROOT=Path(__file__).resolve().parents[1]
class LiveAuditTests(unittest.TestCase):
    def test_live_engine_export_has_no_policy_violations(self):
        out=ROOT/'sample_replay'
        with tempfile.TemporaryDirectory() as folder:
            result=audit(ROOT.parent,out,triggers_path=out/'triggers.jsonl',report_path=Path(folder)/'audit.json')
        self.assertEqual(result['violation_count'],0,result['violations'][:5])
