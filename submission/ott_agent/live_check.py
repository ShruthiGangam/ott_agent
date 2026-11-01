"""Bounded real-provider checks using hand-authored cases, never pack data."""
import argparse
import getpass
import json
import math
import os
import time
from collections import Counter
from pathlib import Path
from .common import write_json
from .provider import Provider, ProviderError

ALLOWED_ENV = {'LLM_API_KEY','LLM_MODEL','LLM_ENDPOINT','LLM_ALLOWED_HOSTS','LLM_PRIVACY_APPROVED','LLM_SYNTHETIC_PACK_AUTHORIZED'}
ALLOWED_ENV.update({'LLM_FALLBACK_API_KEY','LLM_FALLBACK_MODEL','LLM_FALLBACK_ENDPOINT'})
def load_local_env(path):
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if separator and key.strip() in ALLOWED_ENV:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('\"', "'"):
                value = value[1:-1]
            os.environ.setdefault(key.strip(), value)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path,default=Path('.env'))
    parser.add_argument('--prompt-key',action='store_true',help='Read a key in your own terminal without echo')
    parser.add_argument('--model',help='An available model supporting Chat Completions and structured outputs')
    parser.add_argument('--timeout',type=float,default=8)
    parser.add_argument('--out',type=Path,default=Path('live_check_report.json'))
    args=parser.parse_args()
    load_local_env(args.env_file)
    if args.prompt_key:
        os.environ['LLM_API_KEY']=getpass.getpass('Replacement API key (hidden): ')
    if args.model:
        os.environ['LLM_MODEL']=args.model
    os.environ.setdefault('LLM_ENDPOINT','https://api.openai.com/v1/chat/completions')
    os.environ.setdefault('LLM_ALLOWED_HOSTS','api.openai.com')
    report={'test_type':'hand-authored synthetic provider checks; not pack replay or uplift measurement',
        'pack_data_sent':False,'status':'not_started','cases':[], 'max_requests':3}
    try:
        provider=Provider(args.timeout,data_scope='synthetic')
    except (ProviderError,ValueError) as error:
        report.update(status='configuration_blocked',reason=str(error))
        write_json(args.out,report)
        print(json.dumps({'status':report['status'],'reason':report['reason'],'report':str(args.out)}))
        return 2
    # These values are deliberately hand-authored, not derived from any viewer.
    samples=[(['G01'],0,0), (['G02','G03'],1,0), (['G08','G09'],1,1)]
    for number,(goals,plays,completions) in enumerate(samples,1):
        started=time.perf_counter()
        row={'case':number,'eligible_goal_count':len(goals)}
        try:
            proposal=provider.choose(goals,plays,completions)
            row.update(status='accepted',goal_id=proposal['goal_id'],usage=dict(provider.last_usage),model=provider.last_response_model)
        except ProviderError as error:
            row.update(status='failed',error=str(error))
        row['latency_ms']=round((time.perf_counter()-started)*1000,3)
        report['cases'].append(row)
        if row.get('error') in ('remote_http_401','remote_http_403','remote_http_429'):
            break
    accepted=sum(r['status']=='accepted' for r in report['cases'])
    latencies=sorted(r['latency_ms'] for r in report['cases'])
    report.update(status='completed',attempts=len(report['cases']),accepted=accepted,
        accepted_rate=accepted/len(report['cases']), errors=dict(Counter(r['error'] for r in report['cases'] if 'error' in r)),
        p95_latency_ms=latencies[max(0, math.ceil(len(latencies)*.95)-1)],
        token_usage={k:sum(r.get('usage',{}).get(k,0) for r in report['cases']) for k in ('prompt_tokens','completion_tokens','total_tokens')},
        interpretation='Provider connectivity and constrained-output checks only. No claim of targeting quality, uplift, or calibrated confidence.')
    write_json(args.out,report)
    print(json.dumps({'status':report['status'],'attempts':report['attempts'],'accepted':accepted,'report':str(args.out)}))
    return 0 if accepted==len(samples) else 1
if __name__=='__main__':
    raise SystemExit(main())
