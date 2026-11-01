"""Key-free evaluator provider. Reuses real replies; never invents LLM outputs."""
import hashlib
import json
import time
from pathlib import Path
from typing import Protocol
from .common import jsonl
from .prompts import PROMPT_SHA256
from .provider import ProviderError, validate_context
from .validation import ResponseValidationError, validate_plan_response

ASSETS=Path(__file__).resolve().parent/'assets'

class ModelProvider(Protocol):
    """Engine boundary: implementations can be supplied without personal keys."""
    timeout: float
    mode: str
    config: tuple
    last_usage: dict
    last_response_model: str | None
    last_attempts: list
    last_network_request: bool
    last_request_cached: bool
    def plan(self,context,fault=None,unavailable=False): ...

def request_key(context):
    return hashlib.sha256(json.dumps({'prompt_sha256':PROMPT_SHA256,'context':context},sort_keys=True).encode()).hexdigest()

class RecordedProvider:
    mode='recorded'
    def __init__(self,path=None,timeout=.02):
        self.path=Path(path) if path else ASSETS/'recorded_responses.jsonl'
        self.timeout=timeout
        self.config=('recorded://bundled-replies','','recorded-real-llm-replies')
        self.secondary=None
        self.rows={}
        for row in jsonl(self.path):
            if row.get('prompt_sha256')!=PROMPT_SHA256:
                raise ProviderError('recorded_prompt_version_mismatch')
            validate_context(row['context'])
            try:
                validate_plan_response(row['proposal'],row['context'])
            except ResponseValidationError:
                raise ProviderError('recorded_fixture_invalid') from None
            self.rows.setdefault(request_key(row['context']),row)
        self._reset()
    def _reset(self):
        self.last_usage={}
        self.last_response_model=None
        self.last_attempts=[]
        self.last_network_request=False
        self.last_request_cached=False
    def plan(self,context,fault=None,unavailable=False):
        self._reset()
        context=validate_context(context)
        if unavailable:
            raise ProviderError('model_provider_unavailable')
        if fault:
            if fault['fault']=='timeout':
                time.sleep(min(self.timeout,float(fault.get('seconds',self.timeout))))
                raise ProviderError('model_timeout')
            try:
                return validate_plan_response(fault['model_output'],context)
            except ResponseValidationError:
                raise ProviderError('model_output_rejected') from None
        row=self.rows.get(request_key(context))
        if not row:
            raise ProviderError('recorded_response_unavailable')
        try:
            proposal=validate_plan_response(row['proposal'],context)
        except ResponseValidationError:
            raise ProviderError('model_output_rejected') from None
        self.last_response_model=row['response_model']
        self.last_attempts=[{'model':row['response_model'],'source':'recorded_fixture',
            'status':'accepted','network':False,'cached':False,'latency_ms':0}]
        return proposal
