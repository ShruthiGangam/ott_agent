"""Outcome judgments and fixed-cohort randomized-arm measurement."""
import math
from collections import defaultdict
from datetime import timedelta
from .common import csv_rows, event_time, iso, jsonl, ts, write_json, write_jsonl

def difference(success_a, total_a, success_b, total_b):
    if not total_a or not total_b:
        return None
    a, b = success_a/total_a, success_b/total_b
    se = math.sqrt(a*(1-a)/total_a + b*(1-b)/total_b)
    return {'difference_pp': 100*(a-b), 'approx_95ci_pp': [100*(a-b-1.96*se), 100*(a-b+1.96*se)]}

def evaluate(agent, out, triggers, seed):
    # Source observation horizon is the simulator's actual latest server receipt.
    events = list(jsonl(out / 'sim/outcome_events.jsonl'))
    observation_end = max(ts(e['received_at']) for e in events)
    with agent.store.db:
        for event in events:
            agent.store.add_event(event)
        users = {e['user_id'] for e in triggers}
        for uid in sorted(users):
            agent.reconcile(uid, observation_end, complete_observation=True)
            for goal in agent.store.goals(uid, open_only=True):
                goal.update(outcome_judgment='inconclusive', reason='Observation horizon ends before goal deadline', causal_claim=False)
                agent.store.put_goal(goal)
        for state in agent.store.export_rows('viewer_state'):
            uid = state['user_id']
            state['goal_outcomes'] = agent.store.goals(uid)
            active = agent.store.goals(uid, open_only=True)
            state['active_goal'] = active[0] if active else None
            plan=state.get('active_plan') or {}
            plan_expired=plan.get('type')=='home_page' and ts(plan['published_at'])+timedelta(minutes=agent.interventions['home_page'].get('ttl_minutes',120))<=observation_end
            if not active or plan_expired:
                state['active_plan']=None
                state['needs_replan']=True
                agent.store.cancel_plan(uid,iso(observation_end),'Page TTL expired' if plan_expired else 'Goal closed during outcome evaluation')
            state['learning'] = {'observed_successes': sum(g['status'] == 'succeeded' for g in state['goal_outcomes']),
                'reason': 'Retain signal evidence; individual success is not proof of agent causation.', 'as_of': iso(observation_end)}
            agent.store.save_state(uid, state)
    goals = agent.store.export_rows('goals')
    write_jsonl(out / 'outcomes.jsonl', goals)
    # Cohort is all unique triggered users, defined using inputs, regardless of service,
    # goal choice, provider availability, or later outcomes. Every user counts once.
    replay_start = min(ts(e['deliver_at']) for e in triggers)
    end = replay_start + timedelta(days=7)
    observed = defaultdict(set)
    exposed = set()
    for event in events:
        when, lag = event_time(event)
        if event['event'] == 'home_page_shown' and event['properties'].get('personalised'):
            exposed.add(event['user_id'])
        if replay_start <= when <= end and lag >= 0:
            observed[event['event']].add(event['user_id'])
    metrics = {}
    for name in ('play_started', 'episode_completed', 'purchase_completed'):
        valid = observed[name]
        if name == 'purchase_completed':
            valid = {e['user_id'] for e in events if e['event'] == name and e['properties'].get('is_trial') is False
                     and replay_start <= event_time(e)[0] <= end}
        groups = {}
        for arm in ('agent', 'holdout'):
            cohort = {u for u in users if agent.arms.get(u) == arm}
            wins = len(cohort & valid)
            groups[arm] = {'users': len(cohort), 'successes': wins, 'rate': wins/len(cohort) if cohort else None}
        metrics[name] = {**groups, 'comparison': difference(groups['agent']['successes'], groups['agent']['users'],
            groups['holdout']['successes'], groups['holdout']['users'])}
    pilot = csv_rows(agent.pack / 'pilot/pilot_outcomes.csv')
    pilot_groups = {arm: [r for r in pilot if r['arm'] == arm] for arm in ('treatment', 'holdout')}
    pilot_rates = {arm: sum(r['succeeded'] == 'true' for r in rows)/len(rows) for arm, rows in pilot_groups.items()}
    report = {'seed': seed, 'cohort': 'all unique users in input trigger stream, including late triggers; assigned arms; no service filtering',
        'window_start': iso(replay_start), 'window_end': iso(end), 'metrics': metrics,
        'goal_definition_groups':{group:{'goals':sum(bool(g.get('interpretation'))==(group=='provisional') for g in goals),
            'succeeded':sum(g['status']=='succeeded' and bool(g.get('interpretation'))==(group=='provisional') for g in goals)} for group in ('original','provisional')},
        'unique_users_with_recorded_page_exposure': len(exposed), 'goal_status_counts': dict(__import__('collections').Counter(g['status'] for g in goals)),
        'pilot_randomized_rates': pilot_rates, 'causal_scope': 'Simulation only. Approximate unadjusted 95% intervals; no real-world causal claim.'}
    write_json(out / 'impact_report.json', report)
    lines = ['# Impact report', '', 'Fixed 7-day outcomes, using every unique triggered user once in their assigned arm. No filtering by whether the agent served them.', '',
             '| Metric | Agent | Holdout | Difference (pp) | Approx. 95% CI (pp) |', '|---|---:|---:|---:|---:|']
    for name, metric in metrics.items():
        a, b, comp = metric['agent'], metric['holdout'], metric['comparison']
        if comp:
            lines.append(f"| {name} | {a['successes']}/{a['users']} ({a['rate']:.2%}) | {b['successes']}/{b['users']} ({b['rate']:.2%}) | {comp['difference_pp']:.2f} | {comp['approx_95ci_pp'][0]:.2f} to {comp['approx_95ci_pp'][1]:.2f} |")
    lines += ['', 'Intervals are approximate and unadjusted for multiple metrics. Goal attainment is descriptive because goals differ across viewers. Observed success after a page is not individual causal attribution.', '',
        f"Pilot randomized treatment success: {pilot_rates['treatment']:.2%}; holdout: {pilot_rates['holdout']:.2%}. The served-versus-everyone headline is selection-biased.", '',
        'These are simulator results, not evidence of production uplift. A second seed and unseen replay can change results.']
    (out / 'impact_report.md').write_text('\n'.join(lines), encoding='utf-8')
    return report
