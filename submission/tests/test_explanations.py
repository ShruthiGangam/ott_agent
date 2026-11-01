import csv
import hashlib
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
import test_agent as fixtures
from ott_agent.common import iso, write_jsonl
from ott_agent.explanations import explain, export_responses


class ExplanationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AgentTests()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def test_new_decision_records_actual_eligibility_and_sources(self):
        d = self.fixture.decide()
        self.assertEqual(d['planning']['play_events_observed'], 0)
        self.assertEqual(d['planning']['facts']['signup_at']['source'], 'profile:test')
        self.assertIn('signup age is 1.0 days', d['final_reason'])
        self.assertIn('0 plays were observed', d['final_reason'])
        self.assertIn('Success signal: play_started', d['final_reason'])
        self.assertIn('dialect d2', d['final_reason'])
        self.assertEqual(d['explanation']['source'], 'decision_time_trace')
        self.assertEqual(self.fixture.store.decision('trigger')['final_reason'], d['final_reason'])

    def test_late_trigger_explains_age_without_claiming_a_fresh_read(self):
        d = self.fixture.decide(fixtures.event(occurred_at=iso(fixtures.NOW-timedelta(days=2))))
        self.assertIn('172800', d['final_reason'])
        self.assertIn('freshness limit 600', d['final_reason'])
        self.assertFalse(d['planning']['fresh_evidence_read'])
        self.assertEqual(d['model_calls'], 0)
        self.assertNotIn('G05 is eligible', d['final_reason'])

    def test_holdout_reason_does_not_attribute_a_choice_to_the_model(self):
        self.fixture.agent.arms['TEST'] = 'holdout'
        d = self.fixture.decide()
        self.assertIn('randomized holdout', d['final_reason'])
        self.assertNotIn('model selected', d['final_reason'].lower())
        self.assertEqual(d['model_calls'], 0)

    def test_model_failure_explains_verified_local_fallback(self):
        self.fixture.agent._apply_control({'type':'dependency_unavailable','dependency':'model_provider',
            'at':iso(fixtures.NOW-timedelta(seconds=1)),'until':iso(fixtures.NOW+timedelta(minutes=1))})
        d = self.fixture.decide()
        self.assertIn('No model proposal was accepted (model_provider_unavailable)', d['final_reason'])
        self.assertIn('local fallback selected the first eligible goal G01', d['final_reason'])
        self.assertNotIn('The model cited', d['final_reason'])

    def test_existing_page_explains_why_it_is_not_republished(self):
        self.fixture.decide()
        d = self.fixture.decide(fixtures.event('second', when=fixtures.NOW+timedelta(minutes=1)))
        self.assertEqual(d['action'], 'NO_ACTION')
        self.assertIn('Reusing it avoids a duplicate intervention', d['final_reason'])
        self.assertIn('Retained the existing G01', d['final_reason'])

    def test_conflicting_billing_does_not_explain_a_never_paid_goal(self):
        self.fixture.store.add_event(fixtures.event('purchase','purchase_completed',fixtures.NOW-timedelta(minutes=2),
            properties={'plan_id':'P_MONTH','is_trial':False,'price_inr':149}))
        d = self.fixture.decide()
        self.assertNotIn('G05', d['planning']['eligible_goal_ids'])
        self.assertIn('billing event overrides', d['final_reason'])
        self.assertEqual(d['planning']['facts']['subscription_status']['source'], 'event:purchase')

    def test_historical_export_preserves_original_evidence_and_labels_limits(self):
        d = self.fixture.decide()
        for key in ('planning','explanation','final_reason','reason_code'):
            d.pop(key, None)
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            write_jsonl(run/'decisions.jsonl', [d])
            write_jsonl(run/'actions.jsonl', self.fixture.store.export_rows('actions'))
            before = hashlib.sha256((run/'decisions.jsonl').read_bytes()).hexdigest()
            export_responses(run)
            self.assertEqual(before, hashlib.sha256((run/'decisions.jsonl').read_bytes()).hexdigest())
            with (run/'responses.csv').open(encoding='utf-8-sig', newline='') as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row['explanation_source'], 'historical_record_rendering')
            self.assertIn('Detailed entry counts were not retained', row['final_reason'])
            self.assertNotIn('signup age is 1.0', row['final_reason'])

    def test_explanation_cannot_read_a_later_success(self):
        d = self.fixture.decide()
        before = json.dumps(d['explanation'], sort_keys=True)
        self.fixture.store.add_event(fixtures.event('future_purchase','purchase_completed',fixtures.NOW+timedelta(minutes=2),
            properties={'plan_id':'P_MONTH','is_trial':False}))
        self.assertEqual(before, json.dumps(explain(d, self.fixture.store.export_rows('actions')[0]), sort_keys=True))


if __name__ == '__main__':
    unittest.main()
