import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from ott_agent.live_check import load_local_env
from ott_agent.provider import Provider, ProviderError

class LiveConfigurationTests(unittest.TestCase):
    def test_synthetic_checks_do_not_approve_pack_transmission(self):
        env={'LLM_ENDPOINT':'https://api.openai.com/v1/chat/completions','LLM_ALLOWED_HOSTS':'api.openai.com',
             'LLM_MODEL':'test-model','LLM_API_KEY':'test-secret','LLM_PRIVACY_APPROVED':'false'}
        with patch.dict(os.environ,env,clear=True):
            Provider(data_scope='synthetic')
            with self.assertRaisesRegex(ProviderError,'privacy'):
                Provider(data_scope='pack')
    def test_env_file_is_parsed_as_data_and_existing_env_wins(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'LLM_MODEL':'existing'},clear=True):
            path=Path(folder)/'.env'
            path.write_text('LLM_API_KEY="test-secret"\nLLM_MODEL=other\nUNRELATED=ignored\n# comment\n')
            load_local_env(path)
            self.assertEqual(os.environ['LLM_API_KEY'],'test-secret')
            self.assertEqual(os.environ['LLM_MODEL'],'existing')
            self.assertNotIn('UNRELATED',os.environ)
    def test_openai_request_disables_storage_and_uses_closed_schema(self):
        raw=json.dumps({'choices':[{'message':{'content':'{"goal_id":"G01","confidence":0.7}'}}],
                        'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}).encode()
        response=Mock()
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=False)
        response.fp=SimpleNamespace(raw=SimpleNamespace(_sock=Mock()))
        response.read1=Mock(side_effect=[raw,b''])
        opener=Mock()
        opener.open.return_value=response
        with patch.object(Provider,'validate_environment',return_value=('https://api.openai.com/v1/chat/completions','TEST','gpt-5-test')):
            provider=Provider(timeout=1)
        with patch('urllib.request.build_opener',return_value=opener):
            provider.choose(['G01'],0,0)
        body=json.loads(opener.open.call_args.args[0].data)
        self.assertFalse(body['store'])
        self.assertNotIn('temperature',body)
        self.assertEqual(body['max_completion_tokens'],80)
        self.assertTrue(body['response_format']['json_schema']['strict'])
        self.assertFalse(body['response_format']['json_schema']['schema']['additionalProperties'])
        self.assertEqual(provider.last_usage['total_tokens'],15)
    def test_eof_closes_response_fp_without_losing_completion(self):
        payload=json.dumps({'model':'gpt-5.4-mini-2026-03-17','choices':[{'message':{'content':'{"goal_id":"G01","confidence":0.7}'}}]}).encode()
        response=Mock()
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=False)
        response.fp=SimpleNamespace(raw=SimpleNamespace(_sock=Mock()))
        def last_chunk(*args):
            response.fp=None
            return payload
        response.read1=Mock(side_effect=last_chunk)
        opener=Mock()
        opener.open.return_value=response
        with patch.object(Provider,'validate_environment',return_value=('https://api.openai.com/v1/chat/completions','TEST','gpt-5.4-mini')):
            provider=Provider(timeout=1)
        with patch('urllib.request.build_opener',return_value=opener):
            self.assertEqual(provider.choose(['G01'],0,0)['goal_id'],'G01')
        self.assertEqual(provider.last_response_model,'gpt-5.4-mini-2026-03-17')
