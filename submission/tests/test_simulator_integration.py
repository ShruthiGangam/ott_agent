import hashlib
import json
import unittest
from pathlib import Path
from ott_agent.common import jsonl, ts, event_time
ROOT=Path(__file__).resolve().parents[1]
PACK=ROOT.parent
class SimulatorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.out=ROOT/'sample_replay'
        self.report=json.loads((self.out/'manifest.json').read_text())
    def test_supplied_simulator_was_not_modified(self):
        current=hashlib.sha256((PACK/'simulator/simulate_outcomes.py').read_bytes()).hexdigest()
        self.assertEqual(current,self.report['simulator_sha256'])
    def test_simulator_validated_every_published_action(self):
        full=json.loads((ROOT/'benchmarks/live_full/completion_report.json').read_text())
        simulator=json.loads((ROOT/'benchmarks/live_full/sim/simulator_report.json').read_text())
        self.assertEqual(sum(full['actions_by_channel'].values()),simulator['counts']['actions_total'])
        self.assertEqual(full['actions_by_channel']['home_page'],simulator['counts']['home_page_accepted'])
        self.assertEqual(simulator['policy_problem_count'],0)
        self.assertGreater(simulator['events_written'],0)
    def test_success_judgments_have_observed_signals(self):
        events={'event:'+e['event_id']:e for e in jsonl(self.out/'sim/outcome_events.jsonl')}
        for goal in jsonl(self.out/'outcomes.jsonl'):
            if goal['status']=='succeeded':
                self.assertTrue(goal['evidence'])
                for ref in goal['evidence']:
                    self.assertIn(ref,events)
                    e=events[ref]
                    self.assertEqual(e['event'],goal['success']['event'])
                    self.assertLessEqual(ts(goal['started_at']),event_time(e)[0])
                    self.assertLessEqual(event_time(e)[0],ts(goal['deadline']))
                self.assertFalse(goal['causal_claim'])
    def test_exactly_one_supplied_goal_rule_correction(self):
        corrections=[c for c in jsonl(PACK/'replay/control_events.jsonl') if c['type']=='goal_rule_corrected']
        self.assertEqual(len(corrections),1)
        original=json.loads((PACK/'config/goals.json').read_text())
        g03=next(g for g in original['goals'] if g['goal_id']=='G03')
        self.assertEqual(g03['success']['event'],'app_open')
        self.assertEqual(corrections[0]['new_success']['event'],'play_started')
        self.assertEqual(g03['success']['window_hours'],48)
