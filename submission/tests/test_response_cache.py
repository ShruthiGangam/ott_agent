import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from ott_agent.provider import Provider,ProviderError,SYSTEM_PROMPT,safe_payload
from ott_agent.response_cache import ResponseCache
class ResponseCacheTests(unittest.TestCase):
    def test_real_reply_is_reused_without_double_counting_tokens(self):
        with tempfile.TemporaryDirectory() as folder:
            raw=json.dumps({'model':'test-response','choices':[{'message':{'content':'{"goal_id":"G01","confidence":0.7}'}}],
                'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}).encode()
            response=Mock()
            response.__enter__=Mock(return_value=response)
            response.__exit__=Mock(return_value=False)
            response.fp=SimpleNamespace(raw=SimpleNamespace(_sock=Mock()))
            response.read1=Mock(side_effect=[raw,b''])
            opener=Mock()
            opener.open.return_value=response
            with patch.object(Provider,'validate_environment',return_value=('https://provider.example/api','TEST','test-model')):
                p=Provider(timeout=1,cache_path=Path(folder)/'cache.json')
            with patch('urllib.request.build_opener',return_value=opener):
                first=p.choose(['G01'],0,0)
                self.assertEqual(p.last_usage['total_tokens'],15)
                second=p.choose(['G01'],0,0)
            self.assertEqual(first,second)
            self.assertEqual(opener.open.call_count,1)
            self.assertTrue(p.last_request_cached)
            self.assertFalse(p.last_network_request)
            self.assertEqual(p.last_usage,{})
    def test_injected_fault_takes_precedence_over_cached_reply(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(Provider,'validate_environment',return_value=('https://provider.example/api','TEST','test-model')):
            p=Provider(timeout=.01,cache_path=Path(folder)/'cache.json')
            key=p.cache.key(p.config[0],p.config[2],SYSTEM_PROMPT,safe_payload(['G01'],0,0))
            p.cache.put(key,{'goal_id':'G01','confidence':.7},'test-response')
            with self.assertRaisesRegex(ProviderError,'model_timeout'):
                p.choose(['G01'],0,0,fault={'fault':'timeout','seconds':45})
            self.assertFalse(p.last_request_cached)
    def test_cache_key_changes_with_any_model_input(self):
        original=ResponseCache.key('https://provider.example/api','a',SYSTEM_PROMPT,safe_payload(['G01'],0,0))
        for model,prompt,payload in [('b',SYSTEM_PROMPT,safe_payload(['G01'],0,0)),('a','different',safe_payload(['G01'],0,0)),
            ('a',SYSTEM_PROMPT,safe_payload(['G01','G02'],0,0)),('a',SYSTEM_PROMPT,safe_payload(['G01'],1,0))]:
            self.assertNotEqual(original,ResponseCache.key('https://provider.example/api',model,prompt,payload))
    def test_expired_reply_is_not_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            c=ResponseCache(Path(folder)/'cache.json')
            with patch('time.time',return_value=100):
                c.put('key',{'goal_id':'G01','confidence':.7},'response')
            with patch('time.time',return_value=90000):
                self.assertIsNone(c.get('key'))
