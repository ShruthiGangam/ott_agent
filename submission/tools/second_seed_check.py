"""A second simulator seed checks measurement sensitivity, without extra LLM calls."""
import json
import subprocess
import sys
from pathlib import Path
from datetime import timedelta
from ott_agent.common import csv_rows,event_time,jsonl,ts,write_json
from ott_agent.measurement import difference

def check(run,pack,seed='oua-validation-2'):
    run,pack=Path(run).resolve(),Path(pack).resolve()
    target=run/'second_seed_sim'
    subprocess.run([sys.executable,str(pack/'simulator/simulate_outcomes.py'),'--pack',str(pack),'--actions',str(run/'actions.jsonl'),
        '--out',str(target),'--seed',seed],check=True)
    triggers=list(jsonl(pack/'replay/triggers.jsonl'))
    users={e['user_id'] for e in triggers}
    arms={r['user_id']:r['arm'] for r in csv_rows(pack/'replay/arms.csv')}
    start=min(ts(e['deliver_at']) for e in triggers)
    end=start+timedelta(days=7)
    events=list(jsonl(target/'outcome_events.jsonl'))
    metrics={}
    for name in ['play_started','episode_completed','purchase_completed']:
        successful=set()
        for e in events:
            when,lag=event_time(e)
            if e['event']==name and lag>=0 and start<=when<=end and (name!='purchase_completed' or e['properties'].get('is_trial') is False):
                successful.add(e['user_id'])
        groups={}
        for arm in ['agent','holdout']:
            cohort={u for u in users if arms.get(u)==arm}
            groups[arm]={'users':len(cohort),'successes':len(cohort&successful)}
            groups[arm]['rate']=groups[arm]['successes']/groups[arm]['users']
        metrics[name]={**groups,'comparison':difference(groups['agent']['successes'],groups['agent']['users'],groups['holdout']['successes'],groups['holdout']['users'])}
    report={'seed':seed,'same_actions_as_primary_run':True,'additional_llm_calls':0,'metrics':metrics,
        'scope':'Secondary simulator-seed sensitivity check only; goal judgments from the primary run are not overwritten.'}
    write_json(run/'second_seed_impact_report.json',report)
    print(json.dumps(report))
if __name__=='__main__':
    check(sys.argv[1],sys.argv[2])
