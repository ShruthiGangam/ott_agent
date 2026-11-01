import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ott_agent.recorded_provider import RecordedProvider
from ott_agent.provider import ProviderError
from ott_agent.validation import validate_plan_response

class RecordedProviderTests(unittest.TestCase):
    def test_real_recordings_work_without_key_environment_or_network(self):
        with patch.dict(os.environ,{},clear=True),patch('socket.create_connection',side_effect=AssertionError('Network forbidden')):
            provider=RecordedProvider()
            row=next(iter(provider.rows.values()))
            value=provider.plan(row['context'])
        self.assertEqual(value,row['proposal'])
        self.assertFalse(provider.last_network_request)
        self.assertFalse(provider.last_request_cached)
        self.assertEqual(provider.last_usage,{})
        self.assertEqual(provider.mode,'recorded')
        self.assertEqual(provider.last_attempts[0]['source'],'recorded_fixture')
    def test_missing_context_is_not_fabricated_as_an_llm_reply(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'empty.jsonl'; path.write_text('')
            provider=RecordedProvider(path)
            from test_validation import context
            with self.assertRaisesRegex(ProviderError,'recorded_response_unavailable'):
                provider.plan(context())
            self.assertFalse(provider.last_network_request)
    def test_known_faults_override_a_recorded_response(self):
        provider=RecordedProvider()
        row=next(iter(provider.rows.values()))
        with self.assertRaisesRegex(ProviderError,'model_output_rejected'):
            provider.plan(row['context'],fault={'fault':'unsupported_claim','model_output':{'goal_id':'G04','eligible':True}})
        with self.assertRaisesRegex(ProviderError,'unavailable'):
            provider.plan(row['context'],unavailable=True)
    def test_recorded_bank_contains_only_valid_minimized_contracts(self):
        provider=RecordedProvider()
        self.assertGreater(len(provider.rows),0)
        for row in provider.rows.values():
            validate_plan_response(row['proposal'],row['context'])
            self.assertNotIn('user_id',json.dumps(row['context']))
