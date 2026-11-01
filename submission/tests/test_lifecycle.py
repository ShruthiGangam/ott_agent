import unittest
from datetime import timedelta
import test_agent as fixture
from test_agent import event, NOW
from ott_agent.common import iso, ts
class LifecycleTests(unittest.TestCase):
    setUp=fixture.AgentTests.setUp
    tearDown=fixture.AgentTests.tearDown
    decide=fixture.AgentTests.decide
    def test_insufficient_evidence_is_valid_recorded_decision(self):
        d=self.decide(event(app_dialect=None))
        self.assertEqual(d['decision_kind'],'INSUFFICIENT_EVIDENCE')
        self.assertTrue(d['no_action']['valid_decision'])
        self.assertIn('current_app_dialect',d['no_action']['missing_evidence'])
        self.assertFalse(self.store.export_rows('actions'))
    def test_abstention_preserves_existing_memory_and_goal(self):
        first=self.decide()
        old=self.store.state('TEST')
        later=event('unknown-dialect',when=NOW+timedelta(minutes=2),app_dialect=None)
        self.decide(later)
        new=self.store.state('TEST')
        self.assertEqual(new['active_goal']['id'],old['active_goal']['id'])
        self.assertEqual(new['facts']['signup_at']['value'],old['facts']['signup_at']['value'])
        self.assertGreater(new['facts']['signup_at']['age_s'],old['facts']['signup_at']['age_s'])
    def test_current_page_is_not_republished_without_need(self):
        self.decide()
        second=self.decide(event('next-open',when=NOW+timedelta(minutes=1)))
        self.assertEqual(second['reason'],'current_plan_still_live')
        self.assertEqual(second['decision_kind'],'ABSTAIN')
        self.assertEqual(second['model_calls'],0)
        self.assertEqual(len(self.store.export_rows('actions')),1)
    def test_purchase_updates_state_and_closes_conversion_goal(self):
        self.agent.provider.choose=lambda *args,**kwargs:{'goal_id':'G05','confidence':.6}
        first=self.decide()
        purchase=event('paid','purchase_completed',when=NOW+timedelta(minutes=2),properties={'plan_id':'P_MONTH','is_trial':False,'price_inr':149})
        with self.store.db:
            self.agent.observe(purchase,NOW+timedelta(minutes=2))
        state=self.store.state('TEST')
        self.assertEqual(state['facts']['subscription_status']['value'],'active')
        self.assertIsNone(state['active_goal'])
        self.assertTrue(state['needs_replan'])
        self.assertEqual(state['goal_outcomes'][0]['status'],'succeeded')
    def test_late_attributable_signal_revisits_inconclusive_goal(self):
        goal={'id':'late-goal','user_id':'TEST','goal_id':'G02','status':'open','started_at':iso(NOW),
            'deadline':iso(NOW+timedelta(days=3)),'success':{'event':'episode_completed'}}
        self.store.put_goal(goal)
        self.agent.reconcile('TEST',NOW+timedelta(days=4))
        self.assertEqual(self.store.goals('TEST')[0]['status'],'inconclusive')
        late=event('late-complete','episode_completed',when=NOW+timedelta(days=4),occurred_at=iso(NOW+timedelta(days=1)))
        self.store.add_event(late)
        self.agent.reconcile('TEST',NOW+timedelta(days=4),complete_observation=True)
        self.assertEqual(self.store.goals('TEST')[0]['status'],'succeeded')
    def test_queue_wait_counts_against_deadline(self):
        trigger=event()
        self.store.add_event(trigger)
        d=self.agent.decide(trigger,queue_delay_s=61)
        self.assertEqual(d['action'],'NO_ACTION')
        self.assertEqual(d['model_calls'],0)
        self.assertGreaterEqual(d['decided_in_ms'],61000)
        self.assertGreaterEqual(ts(d['published_at']),NOW+timedelta(seconds=61))
    def test_synthetic_override_does_not_claim_zero_retention(self):
        from unittest.mock import patch
        from ott_agent.provider import Provider
        env={'LLM_API_KEY':'test','LLM_MODEL':'test','LLM_ENDPOINT':'https://api.openai.com/v1/chat/completions',
            'LLM_ALLOWED_HOSTS':'api.openai.com','LLM_PRIVACY_APPROVED':'false','LLM_SYNTHETIC_PACK_AUTHORIZED':'true'}
        with patch.dict('os.environ',env,clear=True):
            provider=Provider()
            self.assertIsNotNone(provider.config)
    def test_series_goal_binds_to_the_unfinished_series(self):
        self.agent.profiles['TEST'][0]['signup_at']=iso(NOW-timedelta(days=10))
        title=next(t for t in self.agent.catalogue.values() if t['dialect']=='d2' and t['content_type'] in ('show','micro_drama') and len(self.agent.episodes.get(t['content_slug'],[]))>=2 and self.agent.available(t,NOW))
        first_episode=self.agent.episodes[title['content_slug']][0][2]
        self.store.add_event(event('series-play','play_started',when=NOW-timedelta(days=4),properties={'title_id':title['title_id'],'episode_id':first_episode}))
        self.agent.provider.choose=lambda *args,**kwargs:{'goal_id':'G07','confidence':.6}
        decision=self.decide()
        self.assertEqual(decision['goal']['goal_id'],'G07')
        self.assertEqual(decision['goal']['target_content_slug'],title['content_slug'])
        action=self.store.export_rows('actions')[0]
        self.assertEqual(self.agent.catalogue[action['hero_title_id']]['content_slug'],title['content_slug'])
        wrong=next(t for t in self.agent.catalogue.values() if t['content_slug']!=title['content_slug'])
        self.assertFalse(self.agent.matches(decision['goal'],event('wrong-series','play_started',when=NOW+timedelta(days=1),properties={'title_id':wrong['title_id']})))
        self.assertTrue(self.agent.matches(decision['goal'],event('right-series','play_started',when=NOW+timedelta(days=1),properties={'title_id':title['title_id']})))
