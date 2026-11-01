import json
import unittest
from pathlib import Path
from ott_agent.common import jsonl,event_time,ts
ROOT=Path(__file__).resolve().parents[1]
PACK=ROOT.parent
class SampleReplayValidationTests(unittest.TestCase):
    def setUp(self):
        self.run=ROOT/'sample_replay'
        self.decisions=list(jsonl(self.run/'decisions.jsonl'))
    def test_every_unique_supplied_trigger_has_exactly_one_decision(self):
        supplied={e['event_id'] for e in jsonl(self.run/'triggers.jsonl')}
        recorded=[d['trigger_event_id'] for d in self.decisions]
        self.assertEqual(supplied,set(recorded))
        self.assertEqual(len(recorded),len(set(recorded)))
    def test_no_action_and_missing_evidence_are_explicit(self):
        for d in self.decisions:
            if d['action']=='NO_ACTION':
                self.assertTrue(d['no_action']['valid_decision'])
                self.assertTrue(d['no_action']['reason_code'])
                if d['decision_kind']=='INSUFFICIENT_EVIDENCE':
                    self.assertTrue(d['no_action']['missing_evidence'])
    def test_live_calls_and_cache_are_reported_separately(self):
        original=json.loads((ROOT/'benchmarks/cold_failure/latency_report.json').read_text())
        validated=json.loads((ROOT/'benchmarks/live_full/latency_report.json').read_text())
        self.assertGreater(original['model_sources']['live_llm'],0)
        self.assertGreater(validated['model_sources']['live_llm_cache'],0)
        self.assertEqual(validated['over_60s'],0)
        for d in self.decisions:
            if d.get('model_source')=='live_llm_cache':
                attempts=d.get('model_attempts',[])
                self.assertEqual(d['network_model_calls'],sum(a['network'] for a in attempts))
                if not any(a['network'] for a in attempts):
                    self.assertFalse(d.get('model_usage'))
    def test_goal_success_is_supported_by_observed_viewer_events(self):
        succeeded=[g for g in jsonl(self.run/'outcomes.jsonl') if g['status']=='succeeded']
        needed={ref for g in succeeded for ref in g['evidence']}
        observed={}
        for path in [PACK/'data/events.jsonl',PACK/'replay/triggers.jsonl',PACK/'replay/live_events.jsonl',self.run/'sim/outcome_events.jsonl']:
            for e in jsonl(path):
                ref='event:'+e['event_id']
                if ref in needed:
                    observed[ref]=e
        for g in succeeded:
            self.assertTrue(g['evidence'])
            for ref in g['evidence']:
                self.assertIn(ref,observed)
                e=observed[ref]
                self.assertEqual(e['user_id'],g['user_id'])
                self.assertEqual(e['event'],g['success']['event'])
                self.assertLessEqual(ts(g['started_at']),event_time(e)[0])
                self.assertLessEqual(event_time(e)[0],ts(g['deadline']))
            self.assertFalse(g['causal_claim'])
