"""Exercise the real Agent engine with a live LLM and wholly authored fixtures."""
import argparse
import csv
import json
import math
import hashlib
import subprocess
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path
from .common import iso, ts, jsonl, write_json, write_jsonl
from .engine import Agent
from .live_check import load_local_env
from .provider import Provider
from .store import Store
# Match the unchanged supplied simulator's fixed replay date.
NOW=ts('2026-10-01T09:00:00Z')
def write_csv(path,rows):
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
def event(uid,eid,name='app_open',when=NOW,dialect='d1',**extra):
    result={'user_id':uid,'event_id':eid,'event':name,'occurred_at':iso(when),'sent_at':iso(when),
        'received_at':iso(when),'deliver_at':iso(when),'session_id':eid,'app_dialect':dialect,
        'app_language':'hin','properties':{}}
    result.update(extra)
    return result

def run(out, simulate=False):
    out=Path(out).resolve()
    if out.exists():
        raise ValueError('Use a new output directory to preserve previous evidence')
    out.mkdir(parents=True)
    fixture=out/'authored_fixtures'
    for name in ('data','config','replay'):
        (fixture/name).mkdir(parents=True)
    catalog=[]
    for dialect in ('d1','d2','d3'):
        for index in range(18):
            catalog.append({'title_id':f'DEMO-{dialect}-{index:02}','content_slug':f'demo-{dialect}-{index:02}',
                'title':f'Authored demo {dialect} {index}','dialect':dialect,'language':'hin','content_type':'film',
                'genres':'Drama','release_date':'2026-09-20','available_from':'2026-09-20T00:00:00Z',
                'available_until':'','is_premium':'false','description':'Hand-authored integration test content.'})
    write_csv(fixture/'data/catalogue.csv',catalog)
    write_csv(fixture/'data/episodes.csv',[{'episode_id':t['content_slug']+'-s1e1','content_slug':t['content_slug'],'season':1,'episode':1,'minutes':20} for t in catalog])
    rows=[]
    for uid,status in [('DEMO-NEW','never'),('DEMO-TRIAL','trial_active'),('DEMO-SUBSCRIBER','active'),
        ('DEMO-DIALECT','active'),('DEMO-HOLDOUT','never'),('DEMO-LATE','never'),('DEMO-MISSING','never')]:
        new=uid=='DEMO-NEW'
        rows.append({'user_id':uid,'signup_at':iso(NOW-timedelta(days=1 if new else 45)),
            'subscription_status':status,'plan_started_at':iso(NOW-timedelta(days=1)),
            'plan_ends_at':iso(NOW+timedelta(days=2)) if status in ('active','trial_active') else '',
            'preferred_dialect':'d1','preferred_language':'hin','notifications_opt_in':'false','whatsapp_opt_in':'false',
            'platform':'android','updated_at':iso(NOW-timedelta(hours=1)),'snapshot_at':iso(NOW-timedelta(hours=1))})
    write_csv(fixture/'data/profiles_snapshot.csv',rows)
    write_csv(fixture/'replay/arms.csv',[{'user_id':r['user_id'],'arm':'holdout' if r['user_id']=='DEMO-HOLDOUT' else 'agent'} for r in rows])
    signals={'G01':('play_started',24),'G02':('episode_completed',72),'G03':('app_open',48),
        'G04':('purchase_completed',168),'G05':('purchase_completed',168),'G08':('play_started',168),
        'G09':('play_started',336),'G12':('play_started',168)}
    write_json(fixture/'config/goals.json',{'goals':[{'goal_id':gid,'success':{'event':signal,'window_hours':hours}}
        for gid,(signal,hours) in signals.items()]})
    write_json(fixture/'config/pricing.json',{'plans':[{'plan_id':'DEMO-MONTH','days':30}]})
    write_json(fixture/'config/interventions.json',{'home_page':{'rows':{'max_rows':6,'min_titles_per_row':3,
        'max_titles_per_row':10,'row_types':['genre','new_releases']}},'whatsapp':{'approved_templates':[]}})
    store=Store(out/'state.sqlite')
    with store.db:
        store.add_event(event('DEMO-COVERAGE','coverage','signup_completed',NOW-timedelta(days=30)))
        for row in rows:
            uid=row['user_id']
            store.add_event(event(uid,uid+'-previous',when=NOW-timedelta(days=1)))
        store.add_event(event('DEMO-NEW','new-signup','signup_completed',NOW-timedelta(days=1)))
    write_jsonl(fixture/'data/events.jsonl',[json.loads(r[0]) for r in store.db.execute('SELECT body FROM events ORDER BY received_at')])
    write_jsonl(fixture/'replay/live_events.jsonl',[])
    load_local_env(Path('.env'))
    provider=Provider(timeout=8,data_scope='synthetic')
    agent=Agent(fixture,store,provider,deadline_s=10)
    triggers=[event(r['user_id'],r['user_id']+'-trigger',dialect='d3' if r['user_id']=='DEMO-DIALECT' else 'd1') for r in rows]
    for trigger in triggers:
        if trigger['user_id']=='DEMO-LATE':
            trigger['occurred_at']=iso(NOW-timedelta(days=2))
        if trigger['user_id']=='DEMO-MISSING':
            trigger['app_dialect']=None
    write_jsonl(fixture/'replay/triggers.jsonl',triggers)
    write_jsonl(fixture/'replay/control_events.jsonl',[])
    write_jsonl(fixture/'replay/model_faults.jsonl',[])
    for trigger in triggers:
        with store.db:
            store.add_event(trigger)
            decision=agent.decide(trigger)
        print(json.dumps({'case':trigger['user_id'],'status':decision['status'],'model_calls':decision['model_calls'],
            'fallback':decision.get('model_fallback'),'processing_ms':decision['decided_in_ms']}),flush=True)
    before=len(store.export_rows('actions'))
    with store.db:
        agent.decide(triggers[0])
    duplicate_ok=len(store.export_rows('actions'))==before
    decisions=store.export_rows('decisions')
    actions=store.export_rows('actions')
    by_user={d['user_id']:d for d in decisions}
    checks={
        'new_viewer_plan_verified':by_user['DEMO-NEW']['status']=='PUBLISHED',
        'trial_goal_evidenced':by_user['DEMO-TRIAL']['goal']['goal_id']=='G04',
        'current_dialect_overrides_profile':by_user['DEMO-DIALECT']['dialect']['value']=='d3',
        'holdout_no_action':by_user['DEMO-HOLDOUT']['action']=='NO_ACTION',
        'late_trigger_abstains':by_user['DEMO-LATE']['reason']=='late_or_ambiguous_trigger',
        'missing_dialect_abstains':by_user['DEMO-MISSING']['reason']=='missing_current_app_dialect',
        'duplicate_does_not_publish':duplicate_ok,
        'single_active_goal_per_viewer':all(len(store.goals(r['user_id'],open_only=True))<=1 for r in rows),
        'all_published_actions_verified':all(not d['checks']['failed'] for d in decisions if d['status']=='PUBLISHED')}
    called=[d for d in decisions if d['model_calls']]
    accepted=[d for d in called if not d.get('model_fallback')]
    times=sorted(d['decided_in_ms'] for d in decisions)
    report={'test_type':'real Agent engine with authored fixtures and live OpenAI provider',
        'original_pack_data_sent':False,'provider_mode':'live','actual_response_model':provider.last_response_model,
        'decisions':len(decisions),'published_actions':len(actions),'model_attempts':len(called),
        'accepted_model_decisions':len(accepted),'model_acceptance_rate':len(accepted)/len(called) if called else None,
        'fallbacks':dict(Counter(d['model_fallback'] for d in called if d.get('model_fallback'))),
        'p95_processing_ms':times[max(0,math.ceil(len(times)*.95)-1)],'checks':checks,
        'all_checks_passed':all(checks.values()),
        'scope':'Integration behavior on authored cases; not assignment-pack uplift or a statistical quality estimate.'}
    write_jsonl(out/'decisions.jsonl',decisions)
    write_jsonl(out/'actions.jsonl',actions)
    write_jsonl(out/'viewer_state.jsonl',store.export_rows('viewer_state'))
    if simulate:
        simulator=Path(__file__).resolve().parents[2]/'simulator/simulate_outcomes.py'
        before_hash=hashlib.sha256(simulator.read_bytes()).hexdigest()
        subprocess.run([sys.executable,str(simulator),'--pack',str(fixture),'--actions',str(out/'actions.jsonl'),
            '--out',str(out/'sim'),'--seed','authored-live-integration'],check=True)
        simulation=json.loads((out/'sim/simulator_report.json').read_text())
        observed=list(jsonl(out/'sim/outcome_events.jsonl'))
        observation_end=max(ts(e['received_at']) for e in observed)
        with store.db:
            for e in observed:
                store.add_event(e)
            for uid in by_user:
                agent.reconcile(uid,observation_end,complete_observation=True)
                for goal in store.goals(uid,open_only=True):
                    goal.update(outcome_judgment='inconclusive',reason='Observation horizon ends before deadline')
                    store.put_goal(goal)
            for state in store.export_rows('viewer_state'):
                uid=state['user_id']
                goals=store.goals(uid)
                active=store.goals(uid,open_only=True)
                state.update(goal_outcomes=goals,active_goal=active[0] if active else None)
                store.save_state(uid,state)
        outcomes=store.export_rows('goals')
        write_jsonl(out/'outcomes.jsonl',outcomes)
        write_jsonl(out/'viewer_state.jsonl',store.export_rows('viewer_state'))
        report['simulator']={'script':str(simulator),'script_sha256':before_hash,
            'script_unchanged':hashlib.sha256(simulator.read_bytes()).hexdigest()==before_hash,
            'original_assignment_pack_used':False,'events_generated':simulation['events_written'],
            'policy_problem_count':simulation['policy_problem_count'],'counts':simulation['counts'],
            'goal_outcomes':dict(Counter(g['status'] for g in outcomes)),
            'scope':'Authored integration cases only. Not full supplied-pack validation or uplift evidence.'}
        report['all_checks_passed']=report['all_checks_passed'] and simulation['policy_problem_count']==0 and report['simulator']['script_unchanged']
    write_json(out/'report.json',report)
    store.db.close()
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=Path('live_agent_run'))
    parser.add_argument('--simulate',action='store_true',help='Use the unchanged supplied simulator and judge the goal outcomes')
    args=parser.parse_args()
    report=run(args.out,simulate=args.simulate)
    print(json.dumps(report),flush=True)
    return 0 if report['all_checks_passed'] else 1
if __name__=='__main__':
    raise SystemExit(main())
