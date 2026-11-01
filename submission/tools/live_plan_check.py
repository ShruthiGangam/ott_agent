"""Small uncached live checks of the joint planning prompt and model failover."""
import argparse
import json
import time
from pathlib import Path
from ott_agent.common import write_json
from ott_agent.live_check import load_local_env
from ott_agent.prompts import PROMPT_VERSION,PROMPT_SHA256
from ott_agent.provider import ResilientProvider,ProviderError

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,default=Path('live_plan_check_v2.json'))
    args=parser.parse_args()
    load_local_env('.env')
    rows=[]
    for channel in ('home_page','push','whatsapp','in_app_message','fallback'):
        provider=ResilientProvider(timeout=8,data_scope='synthetic')
        gid='G01' if channel=='home_page' else 'G12'
        actual_channel='home_page' if channel=='fallback' else channel
        context={'eligible_goals':[{'goal_id':gid,'success_event':'play_started','window_hours':24 if gid=='G01' else 168,'rule_version':'2026-09-30'}],
            'evidence':[{'key':'F0','fact':'dialect','value':'d2','freshness':'fresh'},
                {'key':'F1','fact':'language','value':'hin','freshness':'fresh'},
                {'key':'F2','fact':'push_consent','value':True,'freshness':'recent'},
                {'key':'F3','fact':'whatsapp_consent','value':True,'freshness':'recent'}],
            'channel_options':[actual_channel],'active_goal_id':None,
            'activity':{'plays':0 if gid=='G01' else 2,'completions':0}}
        fault={'fault':'malformed_output','model_output':'{broken'} if channel=='fallback' else None
        started=time.monotonic()
        row={'case':channel,'input':context}
        try:
            proposal=provider.plan(context,fault=fault)
            row.update(status='accepted',proposal=proposal,model=provider.last_response_model)
        except ProviderError as error:
            row.update(status='failed',error=str(error))
        row.update(latency_ms=round((time.monotonic()-started)*1000,3),attempts=provider.last_attempts,usage=provider.last_usage)
        rows.append(row)
        print(json.dumps({k:row[k] for k in ('case','status','latency_ms')}),flush=True)
    report={'prompt_version':PROMPT_VERSION,'prompt_sha256':PROMPT_SHA256,'cached':False,
        'data_scope':'hand-authored synthetic summaries; not supplied raw pack records','cases':rows,
        'accepted':sum(r['status']=='accepted' for r in rows),
        'network_requests':sum(a['network'] for r in rows for a in r['attempts']),
        'tokens':sum(r['usage'].get('total_tokens',0) for r in rows)}
    write_json(args.out,report)
    return 0 if report['accepted']==len(rows) else 1

if __name__=='__main__':
    raise SystemExit(main())
