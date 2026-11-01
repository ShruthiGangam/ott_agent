import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ott_agent.provider import Provider,ProviderError
from ott_agent.validation import ResponseValidationError,validate_plan_response,validate_decisions

def context():
    return {'eligible_goals':[{'goal_id':'G01','success_event':'play_started','window_hours':24,'rule_version':'2026-09-30'}],
        'channel_options':['home_page'],'evidence':[{'key':'F0','fact':'dialect','value':'d2','freshness':'fresh'}],
        'active_goal_id':None,'activity':{'plays':0,'completions':0}}

def proposal():
    return {'goal_id':'G01','intervention':'home_page','reason_code':'next_step','evidence_keys':['F0'],'confidence':.7}

class ResponseValidatorTests(unittest.TestCase):
    def test_valid_action_and_explicit_abstention(self):
        self.assertEqual(validate_plan_response(json.dumps(proposal()),context()),proposal())
        self.assertEqual(validate_plan_response(dict(proposal(),goal_id=None,intervention='no_action',evidence_keys=[]),context())['intervention'],'no_action')
    def test_wrong_types_extra_fields_and_fabricated_ids_rejected(self):
        for changes in ({'confidence':'0.7'},{'confidence':True},{'confidence':float('nan')},
            {'confidence':float('inf')},{'confidence':1.5},{'eligible':True},{'goal_id':'G04'},
            {'intervention':'whatsapp'},{'reason_code':'billing_confirmed'},{'evidence_keys':['invented']},
            {'evidence_keys':['F0','F0']},{'goal_id':None},{'evidence_keys':[]}):
            with self.subTest(changes=changes),self.assertRaises(ResponseValidationError):
                validate_plan_response(dict(proposal(),**changes),context())
    def test_duplicate_keys_and_nonstandard_numbers_rejected(self):
        for raw in ('{"goal_id":"G01","goal_id":"G01"}','NaN','Infinity','{broken'):
            with self.subTest(raw=raw),self.assertRaises(ResponseValidationError):
                validate_plan_response(raw,context())
    def test_validation_errors_do_not_echo_source_text(self):
        with self.assertRaises(ResponseValidationError) as caught:
            validate_plan_response(dict(proposal(),secret='DO-NOT-ECHO-THIS'),context())
        self.assertNotIn('DO-NOT-ECHO-THIS',str(caught.exception))
    def test_live_provider_fault_is_rejected_through_formal_validator(self):
        with patch.object(Provider,'validate_environment',return_value=('https://unit.test/api','TEST','TEST')):
            provider=Provider(timeout=.01)
        with self.assertRaisesRegex(ProviderError,'model_output_rejected'):
            provider.plan(context(),fault={'fault':'unsupported_claim','model_output':dict(proposal(),eligible=True)})
    def test_report_detects_bad_saved_proposal(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'decisions.jsonl'
            rows=[{'decision_id':'valid','model_input':context(),'model_proposal':proposal()},
                {'decision_id':'invalid','model_input':context(),'model_proposal':dict(proposal(),goal_id='G04')}]
            path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            report=validate_decisions(path)
            self.assertFalse(report['passed'])
            self.assertEqual(report['accepted_proposals'],1)
            self.assertEqual(report['rejected_count'],1)
            self.assertEqual(report['validator'],'jsonschema.Draft202012Validator')
