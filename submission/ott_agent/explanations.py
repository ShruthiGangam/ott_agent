"""Evidence-backed decision explanations; never invent a model's private rationale."""
import csv
from pathlib import Path
from .common import day, event_time, iso, jsonl, ts, write_jsonl

GOALS = {
    'G01': 'first episode start', 'G02': 'first episode completion',
    'G03': 'return on a later IST day', 'G04': 'trial conversion to paid',
    'G05': 'first paid purchase', 'G06': 'reactivation after lapse',
    'G07': 'resume an unfinished series', 'G08': 'play a recent release',
    'G09': 'play on three distinct IST days', 'G10': 'episode-completion proxy',
    'G11': 'open the actual TV app', 'G12': 'return after absence',
}
REASONS = {
    'holdout_or_unknown_arm': 'No intervention: the viewer is in the randomized holdout or has no approved treatment assignment; serving would invalidate the experiment.',
    'missing_current_app_dialect': 'No intervention: this trigger has no supported current app dialect, so the agent cannot establish which dialect the viewer will see.',
    'no_measurable_eligible_goal': 'No intervention: the observed facts do not establish eligibility for a goal with a measurable success signal.',
    'user_data_store_timeout': 'No intervention: the viewer data store timed out, so fresh evidence could not be verified.',
    'insufficient_budget_for_degraded_store': 'No intervention: the known slow data-store read would consume the remaining decision budget.',
    'insufficient_tool_budget_for_verification': 'No intervention: the remaining read budget cannot cover independent verification.',
    'queue_deadline_exceeded': 'No intervention: queueing exhausted the decision deadline before planning could start.',
    'decision_budget_exceeded': 'No intervention: the decision exceeded its time or read budget before publication.',
    'insufficient_valid_content': 'No intervention: there are too few available, distinct titles in the current display dialect to construct a valid page.',
    'model_insufficient_evidence': 'No intervention: the model explicitly declined to propose an action because its supplied evidence was insufficient.',
    'model_chose_no_action': 'No intervention: the model explicitly proposed no action; the engine respected that abstention.',
    'verification_rejected': 'No intervention: independent verification rejected the proposed action.',
    'publication_revalidation_rejected': 'No intervention: a final evidence read or budget check rejected publication.',
    'safe_abstention': 'No intervention: no independently verified action could be published.',
}


def planning_trace(state, choices, active, now, trigger_id, coverage_start, resume_target=None):
    """Capture already-read evidence before model selection; no tool/model calls."""
    history = state['history']
    facts = state['facts']
    signup = ts(facts.get('signup_at', {}).get('value'))
    plays = [e for e in history if e['event'] == 'play_started']
    completions = [e for e in history if e['event'] == 'episode_completed']
    previous_opens = [e for e in history if e['event'] == 'app_open' and e['event_id'] != trigger_id]
    recent_plays = {day(event_time(e)[0]) for e in plays if 0 <= (now-event_time(e)[0]).total_seconds() <= 14*86400}
    return {
        'as_of': iso(now), 'fresh_evidence_read': True, 'eligible_goal_ids': list(choices),
        'active_goal_before': {k: active[0].get(k) for k in ('id', 'goal_id', 'started_at', 'deadline')} if active else None,
        'facts': facts.copy(), 'history_coverage_start': iso(coverage_start) if coverage_start else None,
        'signup_age_days': round((now-signup).total_seconds()/86400, 3) if signup else None,
        'signup_observed': state['signup_seen'], 'ever_paid_observed': state['ever_paid'],
        'play_events_observed': len(plays), 'completion_events_observed': len(completions),
        'play_days_last_14d': len(recent_plays),
        'prior_opens_last_14d': sum(0 < (now-event_time(e)[0]).total_seconds() <= 14*86400 for e in previous_opens),
        'resume_target': resume_target,
    }


def _fact(trace, name):
    fact = trace.get('facts', {}).get(name)
    if not fact:
        return None
    return f"{name}={fact['value']} (source {fact['source']}, as of {fact['as_of']})"


def _goal_basis(gid, trace, goal):
    active = trace.get('active_goal_before')
    if active and active.get('goal_id') == gid:
        return f"Retained the existing {gid} goal committed at {active.get('started_at')}; entry eligibility belongs to that commitment and the goal remains open until {active.get('deadline')}."
    status = _fact(trace, 'subscription_status')
    signup = _fact(trace, 'signup_at')
    if gid == 'G01' and trace.get('signup_observed'):
        return f"G01 is eligible: signup was observed, signup age is {trace.get('signup_age_days')} days (limit 7), and {trace.get('play_events_observed')} plays were observed since covered signup. {signup}."
    if gid == 'G02' and trace.get('signup_observed'):
        return f"G02 is eligible: signup is covered by observed history and {trace.get('completion_events_observed')} episode completions were observed. {signup}."
    if gid == 'G03' and trace.get('signup_age_days') is not None:
        return f"G03 is eligible because signup age is {trace['signup_age_days']} days (limit 2). {signup}."
    if gid == 'G04' and status:
        return f"G04 is eligible because the resolved subscription is trial_active: {status}. Only a non-trial purchase can satisfy this goal."
    if gid == 'G05' and status:
        return f"G05 is eligible because the resolved status is never and no paid billing event was observed: {status}. This is a claim within available history, not proof of lifetime non-payment."
    if gid == 'G06' and status:
        return f"G06 uses lapsed status and a recorded lapse/expiry: {status}; {_fact(trace, 'lapsed_at')}. The 14-day recency threshold is a documented provisional definition."
    if gid == 'G07' and trace.get('resume_target'):
        target = trace['resume_target']
        return f"G07 is eligible: series {target['content_slug']} was last played at {target['last_play_at']}, at least three days ago, and has {target['remaining_episode_count']} unwatched episodes. Source {target['evidence']}."
    if gid == 'G08' and status:
        return f"G08 uses an active subscription ({status}) and an available title released within the preceding 30 days in the resolved dialect."
    if gid == 'G09' and status and 'play_days_last_14d' in trace:
        return f"G09 is eligible: {status}; {trace['play_days_last_14d']} distinct play days were observed in the last 14 days (entry limit 1), with at least 14 days of coverage."
    if gid == 'G10':
        return 'G10 is offered under the documented provisional definition of meaningful engagement: episode completion within seven days. This definition was not supplied by the original brief.'
    if gid == 'G11' and status:
        return f"G11 uses active subscription evidence: {status}. Success requires an actual tv_app_open event; missing TV telemetry remains inconclusive."
    if gid == 'G12' and 'prior_opens_last_14d' in trace:
        return f"G12 is eligible: the viewer was known before the 14-day absence window and {trace['prior_opens_last_14d']} prior opens were observed in that window; the current trigger is excluded."
    return f"The saved decision committed {gid} with its recorded eligibility evidence. Detailed entry counts were not retained in this historical record; they are not reconstructed from later outcomes."


def explain(decision, action=None):
    """Render only saved decision-time inputs; never consult later viewer outcomes."""
    trace = decision.get('planning', {})
    proposal = decision.get('model_proposal', {})
    context = decision.get('model_input', {})
    goal = decision.get('goal') or {}
    gid = goal.get('goal_id')
    code = decision.get('reason_code', decision.get('reason', 'safe_abstention'))
    acted = decision['action'] != 'NO_ACTION'
    parts = []
    if not acted:
        if code == 'late_or_ambiguous_trigger':
            lag = trace.get('trigger_lag_s')
            age = decision.get('trigger', {}).get('event_age_s')
            parts.append(f"No intervention: this trigger is {age} seconds old (freshness limit 600 seconds) or has ambiguous phone-clock timing" + (f" (send-minus-occur {lag} seconds)." if lag is not None else '.'))
        elif code == 'current_plan_still_live':
            parts.append(f"No new action: the existing {gid} homepage is still within its 120-minute TTL, matches the current dialect, and its titles remain available. Reusing it avoids a duplicate intervention.")
        else:
            parts.append(REASONS.get(code, f"No action was published; recorded decision condition: {code}."))
        failed = decision.get('checks', {}).get('failed', [])
        if failed:
            parts.append('Blocking checks: ' + ', '.join(failed) + '.')
    if gid and (acted or code == 'current_plan_still_live'):
        parts.append(_goal_basis(gid, trace, goal))
    if acted:
        offered = [g['goal_id'] for g in context.get('eligible_goals', [])] or trace.get('eligible_goal_ids', [])
        source = decision.get('model_source', 'not_called')
        if proposal:
            selection = 'Retained' if context.get('active_goal_id') == gid else 'Selected'
            parts.append(f"{selection} {gid} ({GOALS.get(gid, gid)}) from the offered goals {', '.join(offered)} using the {source} proposal; its recorded reason category is {proposal['reason_code']}.")
            cited = [f"{e['key']}: {e['fact']}={e['value']} ({e['freshness']})" for e in context.get('evidence', []) if e['key'] in proposal.get('evidence_keys', [])]
            if cited:
                parts.append('The model cited ' + '; '.join(cited) + '.')
        elif decision.get('model_fallback'):
            parts.append(f"No model proposal was accepted ({decision['model_fallback']}); the local fallback selected the first eligible goal {gid}, then applied independent verification.")
        else:
            parts.append(f"The local planner selected {gid} from eligible goals without an accepted model proposal.")
        dialect = (action or {}).get('dialect') or (decision.get('dialect') or {}).get('value')
        if decision['action'] == 'HOME_PAGE':
            parts.append(f"Published an in-session homepage in dialect {dialect}. Content uses available dialect variants, genre affinity and release-date ordering" + ('; G08 prioritizes recent releases.' if gid == 'G08' else '; G07 prioritizes the unfinished series.' if gid == 'G07' else '.'))
        else:
            parts.append(f"Published one {decision['action'].lower()} reminder in dialect {dialect}; this channel was offered for the eligible lapse/resume/return goal and passed message-policy checks.")
        if goal.get('deadline'):
            parts.append(f"Success signal: {goal.get('success', {}).get('event')} ({goal.get('success', {}).get('condition', 'recorded goal rule')}) by {goal['deadline']}.")
        passed = [c for c in decision.get('checks', {}).get('passed', []) if c != 'recorded_decision']
        parts.append('Independent checks passed: ' + ', '.join(passed) + '.')
    if proposal and not acted:
        parts.append(f"Model proposal: {proposal.get('intervention')}, reason category {proposal.get('reason_code')}; the final action follows the recorded abstention or verifier veto.")
    conflicts = decision.get('conflicts', [])
    if conflicts:
        parts.append('Source conflict handling: ' + '; '.join(dict.fromkeys(c['reason'] for c in conflicts)) + '.')
    return {'version': 1, 'source': 'decision_time_trace' if 'planning' in decision else 'historical_record_rendering',
        'summary': ' '.join(parts), 'reason_code': code,
        'model_reason_code': proposal.get('reason_code'),
        'model_evidence_keys': proposal.get('evidence_keys', []),
        'eligible_goal_ids': [g['goal_id'] for g in context.get('eligible_goals', [])] or trace.get('eligible_goal_ids', []),
        'offered_channels': context.get('channel_options', []),
        'limits': 'Application explanation from recorded facts and checks. The model returned a reason category and evidence keys; it did not provide a comparative free-text rationale or calibrated success probability.'}


def export_responses(run):
    """Rebuild review files without rewriting historical decisions or model replies."""
    run = Path(run)
    actions = {a['decision_id']: a for a in jsonl(run/'actions.jsonl')}
    rows, explanations = [], []
    for d in jsonl(run/'decisions.jsonl'):
        explanation = d.get('explanation') or explain(d, actions.get(d['decision_id']))
        explanations.append({'decision_id': d['decision_id'], 'user_id': d['user_id'], **explanation})
        rows.append({'user_id': d['user_id'], 'trigger_event_id': d['trigger_event_id'],
            'decision_id': d['decision_id'], 'published_at': d['published_at'],
            'goal_id': (d.get('goal') or {}).get('goal_id', ''), 'action': d['action'],
            'decision_kind': d.get('decision_kind', ''), 'reason_code': explanation['reason_code'],
            'final_reason': explanation['summary'], 'explanation_source': explanation['source'],
            'model_reason_code': explanation['model_reason_code'],
            'model_evidence_keys': ';'.join(explanation['model_evidence_keys']),
            'model_source': d.get('model_source', 'not_called'),
            'model_name': d.get('model_name', ''), 'model_fallback': d.get('model_fallback', ''),
            'network_model_calls': d.get('network_model_calls', 0), 'decided_in_ms': d['decided_in_ms'],
            'evidence_sources': ';'.join(sorted({f['source'] for f in d.get('evidence', [])})),
            'checks_passed': ';'.join(d.get('checks', {}).get('passed', [])),
            'checks_failed': ';'.join(d.get('checks', {}).get('failed', []))})
    with (run/'responses.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        if rows:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    write_jsonl(run/'explanations.jsonl', explanations)
    return {'decisions': len(rows), 'responses': str(run/'responses.csv'), 'explanations': str(run/'explanations.jsonl')}
