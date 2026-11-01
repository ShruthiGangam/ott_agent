"""Check the seven assignment requirements against a completed local run."""
import json
import sqlite3
from pathlib import Path
from collections import Counter
from ott_agent.common import jsonl,ts,write_json

def assess(run):
    run=Path(run)
    decisions=list(jsonl(run/'decisions.jsonl'))
    actions=list(jsonl(run/'actions.jsonl'))
    outcomes=list(jsonl(run/'outcomes.jsonl'))
    audit=json.loads((run/'verification_report.json').read_text())
    latency=json.loads((run/'latency_report.json').read_text())
    simulator=json.loads((run/'sim/simulator_report.json').read_text())
    impact=json.loads((run/'impact_report.json').read_text())
    config=json.loads((run/'run_config.json').read_text())
    connection=sqlite3.connect('file:'+(run/'state.sqlite').resolve().as_posix()+'?mode=ro',uri=True)
    states=[json.loads(r[0]) for r in connection.execute('SELECT body FROM viewer_state')]
    ownership_violations=connection.execute("SELECT user_id FROM goals WHERE status='open' GROUP BY user_id HAVING COUNT(*)>1").fetchall()
    connection.close()
    acted=[d for d in decisions if d['action']!='NO_ACTION']
    no_action=[d for d in decisions if d['action']=='NO_ACTION']
    insufficient=[d for d in no_action if d.get('decision_kind')=='INSUFFICIENT_EVIDENCE']
    checks={
        'understand_viewer':all(d.get('evidence') and all({'source','as_of','age_s'}<=set(f) for f in d['evidence']) and 'conflicts' in d for d in acted),
        'choose_measurable_goal_or_explain':all((d.get('goal') and d['goal'].get('deadline') and d['goal'].get('success',{}).get('event')) or (d['action']=='NO_ACTION' and d.get('reason')) for d in decisions),
        'decide_intervention_or_no_action':all(d['action'] in ('HOME_PAGE','PUSH','WHATSAPP','IN_APP_MESSAGE','NO_ACTION') and bool(d.get('reason')) for d in decisions),
        'act_within_budget':latency['over_60s']==0 and latency['max_model_calls']<=config['max_model_calls'] and latency['max_tool_calls']<=config['max_tool_calls'],
        'independent_verification':audit['violation_count']==0 and simulator['policy_problem_count']==0,
        'close_loop':all(g['status'] in ('succeeded','failed','inconclusive') or g.get('outcome_judgment')=='inconclusive' for g in outcomes)
            and all(s.get('learning') is not None for s in states),
        'randomized_impact_measurement':all(impact['metrics'][metric].get('comparison') is not None for metric in ('play_started','episode_completed','purchase_completed')),
        'one_open_goal_per_viewer':not ownership_violations,
        'explicit_valid_no_action':all(d.get('no_action',{}).get('valid_decision') is True for d in no_action),
        'explicit_insufficient_evidence':all(d['no_action'].get('missing_evidence') for d in insufficient)}
    corrections=[g for g in outcomes if g.get('revisions')]
    report={'scope':'Full supplied-pack replay with independently checked homepage/message actions and explicit no-action decisions. Delivery observations come from the unchanged simulator; no real phones contacted.',
        'checks':checks,'all_checks_passed_in_scope':all(checks.values()),
        'decision_count':len(decisions),'viewer_count':len(states),'action_count':len(actions),
        'no_action_count':len(no_action),'insufficient_evidence_count':len(insufficient),
        'no_action_reasons':dict(Counter(d['reason'] for d in no_action)),
        'model_sources':dict(Counter(d.get('model_source','not_called') for d in decisions)),
        'goal_status_counts':dict(Counter(g['status'] for g in outcomes)),
        'goal_ids':dict(Counter(g['goal_id'] for g in outcomes)),
        'corrected_open_goal_instances':len(corrections),'corrected_viewers':len({g['user_id'] for g in corrections}),
        'latency':latency,'simulator_policy_problems':simulator['policy_problem_count'],
        'positive_business_effect_proven':False,
        'effect_note':'Read each randomized difference and uncertainty interval; pipeline completion is not proof of positive uplift.',
        'data_authorization':config.get('data_authorization')}
    write_json(run/'requirements_report.json',report)
    lines=['# Assignment requirements audit','',report['scope'],'','| Requirement/check | Result |','|---|---|']
    for name,passed in checks.items():
        lines.append(f"| {name} | {'PASS' if passed else 'NOT MET'} |")
    lines+=['',f"{len(decisions)} decisions across {len(states)} viewers; {len(actions)} actions; {len(no_action)} recorded no-action decisions, including {len(insufficient)} insufficient-evidence decisions.",'',
        'This report checks implemented behavior and measurements. It does not assert production scale or statistically proven positive impact.']
    (run/'requirements_report.md').write_text('\n'.join(lines),encoding='utf-8')
    return report
if __name__=='__main__':
    import sys
    report=assess(sys.argv[1])
    print(json.dumps({'all_checks_passed':report['all_checks_passed_in_scope'],'checks':report['checks']}))
