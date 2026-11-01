"""Measure local actor/runtime throughput with model calls intentionally disabled."""
import argparse
import json
import math
import time
from datetime import timedelta
from pathlib import Path
from ott_agent.common import iso,jsonl,ts,write_json
from ott_agent.recorded_provider import RecordedProvider
from ott_agent.runtime import ViewerRuntime
from ott_agent.store import Store

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pack',type=Path,default=Path('..'))
    parser.add_argument('--out',type=Path,default=Path('runs/runtime_stress'))
    args=parser.parse_args()
    triggers=sorted(jsonl(args.pack/'replay/triggers.jsonl'),key=lambda e:ts(e['deliver_at']))
    best=[]; left=0
    for right,e in enumerate(triggers):
        while ts(triggers[left]['deliver_at'])<ts(e['deliver_at'])-timedelta(minutes=10):
            left+=1
        if right-left+1>len(best):
            best=triggers[left:right+1]
    arrival=ts(best[-1]['deliver_at'])
    jobs=[]
    for multiple in range(3):
        for i,trigger in enumerate(best):
            # Collapse the entire 3x ten-minute window into an immediate burst.
            jobs.append(dict(trigger,event_id=f'load-{multiple}-{i}',occurred_at=iso(arrival),
                sent_at=iso(arrival),received_at=iso(arrival),deliver_at=iso(arrival)))
    runtime=ViewerRuntime(args.pack,args.out,lambda:RecordedProvider(),shards=4,max_model_calls=0,clock=lambda:arrival)
    runtime.seed(e for e in jsonl(args.pack/'data/events.jsonl') if ts(e['received_at'])<arrival)
    start=time.monotonic()
    try:
        runtime.start()
        duplicates=0
        for job in jobs:
            runtime.enqueue(job)
            duplicates+=runtime.enqueue(job)==0
        runtime.drain(timeout=60)
    finally:
        runtime.close()
    elapsed=time.monotonic()-start
    decisions=[]; violations=0
    for index in range(4):
        store=Store(runtime.path(index))
        decisions.extend(store.export_rows('decisions'))
        violations+=len(store.db.execute("SELECT user_id FROM goals WHERE status='open' GROUP BY user_id HAVING COUNT(*)>1").fetchall())
        store.db.close()
    values=sorted(d['decided_in_ms'] for d in decisions)
    report={'scope':'actual local durable actor workers, deterministic safe path; no network/LLM capacity claim',
        'supplied_peak_deliveries_per_10min':len(best),'multiplier':3,'burst_jobs':len(jobs),
        'burst_was_collapsed_into_seconds':elapsed,'workers':4,'unique_decisions':len(decisions),
        'duplicate_jobs_suppressed':duplicates,'network_calls':sum(d.get('network_model_calls',0) for d in decisions),
        'over_60s':sum(v>60000 for v in values),'p95_ms':values[math.ceil(len(values)*.95)-1],
        'max_ms':max(values),'single_goal_violations':violations,
        'passed':len(decisions)==len(jobs) and not violations and max(values)<=60000}
    write_json(args.out/'stress_report.json',report)
    print(json.dumps(report),flush=True)
    return 0 if report['passed'] else 1

if __name__=='__main__':
    raise SystemExit(main())
