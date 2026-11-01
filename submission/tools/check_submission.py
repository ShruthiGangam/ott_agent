"""Read-only submission inventory/contract checks; no key or network needed."""
import hashlib
import csv
import json
import re
from pathlib import Path
from ott_agent.common import jsonl,write_json
from ott_agent.recorded_provider import RecordedProvider
from ott_agent.validation import validate_decisions

ROOT=Path(__file__).resolve().parents[1]

def check():
    required=['replay.py','pyproject.toml','requirements.txt','README.md','SUBMISSION_CHECKLIST.md',
        'ARCHITECTURE.md','AI_COLLABORATION.md','KNOWN_LIMITATIONS.md','.env.example',
        'ott_agent/store.py','ott_agent/validation.py','ott_agent/recorded_provider.py',
        'ott_agent/explanations.py','tools/package_submission.py','tools/export_responses.py',
        'ott_agent/assets/goal_interpretations.json','ott_agent/assets/recorded_responses.jsonl',
        'sample_replay/decisions.jsonl','sample_replay/actions.jsonl','sample_replay/no_action_decisions.jsonl',
        'sample_replay/viewer_state.jsonl','sample_replay/outcomes.jsonl','sample_replay/impact_report.md',
        'sample_replay/responses.csv','sample_replay/explanations.jsonl',
        'tests/test_agent.py','tests/test_more.py','tests/test_validation.py','tests/test_recorded_provider.py',
        'tests/test_explanations.py','tests/test_packaging.py']
    missing=[name for name in required if not (ROOT/name).is_file()]
    validation=validate_decisions(ROOT/'sample_replay/decisions.jsonl')
    provider=RecordedProvider()
    meta=json.loads((ROOT/'ott_agent/assets/recorded_responses.meta.json').read_text())
    manifest=json.loads((ROOT/'sample_replay/manifest.json').read_text())
    states=list(jsonl(ROOT/'sample_replay/viewer_state.jsonl'))
    readable_path=ROOT/'sample_replay/responses.csv'
    readable=list(csv.DictReader(readable_path.open(encoding='utf-8-sig',newline=''))) if readable_path.exists() else []
    leaked=[]
    for top in ('ott_agent','tests','tools','sample_replay','benchmarks'):
        for path in (ROOT/top).rglob('*'):
            if not path.is_file() or '__pycache__' in path.parts or path.suffix not in ('.py','.json','.jsonl','.md','.toml','.txt'):
                continue
            if re.search(r'sk-(?:proj-)?[A-Za-z0-9_-]{20,}',path.read_text(encoding='utf-8-sig')):
                leaked.append(path.relative_to(ROOT).as_posix())
    for path in list(ROOT.glob('*.md'))+[ROOT/'.env.example',ROOT/'pyproject.toml',ROOT/'requirements.txt']:
        if re.search(r'sk-(?:proj-)?[A-Za-z0-9_-]{20,}',path.read_text(encoding='utf-8-sig')):
            leaked.append(path.relative_to(ROOT).as_posix())
    tests=json.loads((ROOT/'benchmarks/test_report.json').read_text()) if (ROOT/'benchmarks/test_report.json').exists() else {}
    checks={'required_files_present':not missing,'sample_responses_valid':validation['passed'],
        'recording_bank_matches_manifest':len(provider.rows)==meta['entries'] and hashlib.sha256(provider.path.read_bytes()).hexdigest()==meta['sha256'],
        'sample_has_all_selected_viewer_states':{s['user_id'] for s in states}==set(manifest['selected_viewers']),
        'sample_unique_decisions':len({d['trigger_event_id'] for d in jsonl(ROOT/'sample_replay/decisions.jsonl')})==manifest['decisions'],
        'sample_has_readable_explanations':len(readable)==manifest['decisions'] and all(len(r.get('final_reason',''))>60 and r.get('explanation_source') for r in readable),
        'no_api_key_in_shareable_files':not leaked,'tests_passed':tests.get('passed') is True,
        'private_configuration_ignored':all(token in (ROOT.parent/'.gitignore').read_text() for token in ('.env','!.env.example','.venv/','runs/'))}
    result={'checks':checks,'passed':all(checks.values()),'missing_files':missing,
        'files_with_possible_credentials':leaked,'validator':validation,'recorded_contexts':len(provider.rows),
        'tests_run':tests.get('tests_run'),'network_calls':0,
        'scope':'Local deliverable inventory and response-contract check; not fresh-model, deployment or uplift validation.'}
    write_json(ROOT/'benchmarks/submission_check.json',result)
    print(json.dumps(result,indent=2))
    return result

if __name__=='__main__':
    raise SystemExit(0 if check()['passed'] else 1)
