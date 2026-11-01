import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import test_agent as fixture
from test_agent import event, NOW
from datetime import timedelta
from ott_agent.common import iso, ts
from ott_agent.provider import Provider, ProviderError
from ott_agent.store import Store

class MoreAgentTests(unittest.TestCase):
    setUp = fixture.AgentTests.setUp
    tearDown = fixture.AgentTests.tearDown
    decide = fixture.AgentTests.decide
    def test_active_return_goal_survives_another_open(self):
        self.store.put_goal({'id':'return','user_id':'TEST','goal_id':'G12','status':'open',
            'started_at':'2026-09-30T09:00:00Z','deadline':'2026-10-07T09:00:00Z',
            'success':{'event':'play_started'},'rule_version':'v1'})
        self.store.add_event(event('previous', when=NOW-timedelta(seconds=1)))
        state=self.agent.evidence('TEST',NOW)
        self.assertNotIn('G12',self.agent.candidates(state,NOW))
        self.assertIn('G12',self.agent.allowed_goals(state,NOW))
    def test_missing_current_dialect_abstains(self):
        result=self.decide(event(app_dialect=None))
        self.assertEqual(result['reason'],'missing_current_app_dialect')
        self.assertFalse(self.store.export_rows('actions'))
    def test_one_read_budget_is_respected(self):
        self.agent.max_tool_calls=1
        result=self.decide()
        self.assertLessEqual(result['tool_calls'],1)
        self.assertNotEqual(result['status'],'PUBLISHED')
    def test_rule_correction_delivery_is_idempotent(self):
        self.store.put_goal({'id':'r','user_id':'TEST','goal_id':'G03','status':'open',
            'started_at':'2026-09-30T09:00:00Z','deadline':'2026-10-02T09:00:00Z',
            'success':{'event':'app_open'},'rule_version':'v1'})
        control={'type':'goal_rule_corrected','goal_id':'G03','at':iso(NOW),
            'new_success':{'event':'play_started'}}
        self.agent._apply_control(control)
        self.agent._apply_control(control)
        self.assertEqual(len(self.store.goals('TEST')[0]['revisions']),1)

class TransportTests(unittest.TestCase):
    def provider(self):
        with patch.object(Provider,'validate_environment',return_value=('https://provider.example/api','SECRET','model')):
            return Provider(timeout=.03)
    def test_request_has_only_minimized_viewer_data(self):
        raw=json.dumps({'choices':[{'message':{'content':'{"goal_id":"G01","confidence":0.7}'}}]}).encode()
        response=Mock()
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=False)
        response.fp=SimpleNamespace(raw=SimpleNamespace(_sock=Mock()))
        response.read1=Mock(side_effect=[raw,b''])
        opener=Mock()
        opener.open.return_value=response
        with patch('urllib.request.build_opener',return_value=opener):
            result=self.provider().choose(['G01'],1,0)
        request=opener.open.call_args.args[0]
        body=json.loads(request.data)
        payload=json.loads(body['messages'][1]['content'])
        self.assertEqual(set(payload),{'eligible_goal_ids','play_count_bucket','completion_count_bucket'})
        self.assertNotIn('SECRET',request.data.decode())
        self.assertEqual(result['goal_id'],'G01')
    def test_slow_transport_has_wallclock_deadline(self):
        opener=Mock()
        def slow(*args,**kwargs):
            time.sleep(.2)
            raise RuntimeError('SECRET should not be logged')
        opener.open.side_effect=slow
        provider=self.provider()
        with patch('urllib.request.build_opener',return_value=opener):
            started=time.monotonic()
            with self.assertRaisesRegex(ProviderError,'model_timeout'):
                provider.choose(['G01'],0,0)
            self.assertLess(time.monotonic()-started,.15)
            with self.assertRaisesRegex(ProviderError,'still_finishing'):
                provider.choose(['G01'],0,0)
    def test_storage_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.sqlite'
            one=Store(path)
            with one.db:
                one.add_event(event())
                one.put_goal({'id':'g','user_id':'TEST','goal_id':'G01','status':'open'})
            one.db.close()
            two=Store(path)
            self.assertEqual(len(two.history('TEST',iso(NOW))),1)
            self.assertEqual(two.goals('TEST',open_only=True)[0]['id'],'g')
            self.assertFalse(two.add_event(event()))
            two.db.close()
