"""Local JSON Schema validation for live, cached and recorded model responses."""
import json
from collections import Counter
from functools import lru_cache
from importlib.metadata import version
from jsonschema import Draft202012Validator, ValidationError, SchemaError
from .prompts import planning_schema

class ResponseValidationError(ValueError):
    """Categorical message only; never echo the provider's content."""

def closed_json(raw):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:
                raise ResponseValidationError('duplicate_json_key')
            result[key]=value
        return result
    def constant(_):
        raise ResponseValidationError('non_finite_number')
    try:
        if isinstance(raw,str) and len(raw.encode('utf-8'))>65536:
            raise ResponseValidationError('response_too_large')
        value=json.loads(raw,object_pairs_hook=pairs,parse_constant=constant) if isinstance(raw,str) else raw
        if len(json.dumps(value,allow_nan=False).encode('utf-8'))>65536:
            raise ResponseValidationError('response_too_large')
        return value
    except (ValueError,TypeError,RecursionError):
        raise ResponseValidationError('invalid_response_json') from None

@lru_cache(maxsize=256)
def _validator(encoded_schema):
    schema=json.loads(encoded_schema)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)

def _validate(value,schema):
    try:
        _validator(json.dumps(schema,sort_keys=True)).validate(value)
    except (ValidationError,SchemaError):
        raise ResponseValidationError('response_schema_mismatch') from None
    return value

def validate_goal_response(raw,allowed):
    schema={'type':'object','properties':{'goal_id':{'type':'string','enum':list(allowed)},
        'confidence':{'type':'number','minimum':0,'maximum':1}},
        'required':['goal_id','confidence'],'additionalProperties':False}
    return _validate(closed_json(raw),schema)

def validate_plan_response(raw,context):
    schema=planning_schema([g['goal_id'] for g in context['eligible_goals']],context['channel_options'],[e['key'] for e in context['evidence']])
    # Additional local rules do not depend on the hosted schema implementation.
    schema['properties']['evidence_keys'].update(maxItems=12,uniqueItems=True)
    value=_validate(closed_json(raw),schema)
    if value['intervention']!='no_action' and (value['goal_id'] is None or not value['evidence_keys']):
        raise ResponseValidationError('action_requires_goal_and_evidence')
    return value

def validate_decisions(path):
    from .common import jsonl
    accepted=Counter(); rejected=[]; total=0
    for row in jsonl(path):
        total+=1
        if 'model_proposal' not in row:
            continue
        try:
            validate_plan_response(row['model_proposal'],row['model_input'])
            accepted[row.get('model_source','unknown')]+=1
        except (ResponseValidationError,KeyError,TypeError):
            rejected.append({'decision_id':row.get('decision_id'),'error':'model_output_rejected'})
    return {'validator':'jsonschema.Draft202012Validator','library_version':version('jsonschema'),
        'decisions_scanned':total,'accepted_proposals':sum(accepted.values()),
        'accepted_by_source':dict(accepted),'rejected_count':len(rejected),'rejected':rejected,
        'passed':not rejected,'scope':'Response contract only; factual eligibility and action safety require independent checks.'}
