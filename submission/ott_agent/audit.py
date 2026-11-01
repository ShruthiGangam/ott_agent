"""Independently inspect exported actions against source policies and controls."""
from collections import Counter
import json
from datetime import timedelta
from .common import csv_rows, event_time, iso, jsonl, ts, write_json
from .messaging import MESSAGE_CHANNELS, verify_message

def audit(pack, out, triggers_path=None, report_path=None):
    catalogue={r['title_id']:r for r in csv_rows(pack/'data/catalogue.csv')}
    arms={r['user_id']:r['arm'] for r in csv_rows(pack/'replay/arms.csv')}
    triggers={}
    for trigger in sorted(jsonl(triggers_path or pack/'replay/triggers.jsonl'), key=lambda e: ts(e['deliver_at'])):
        triggers.setdefault(trigger['event_id'],trigger)
    withdrawn={r['title_id']:ts(r['at']) for r in jsonl(pack/'replay/control_events.jsonl') if r['type']=='title_withdrawn'}
    decisions=list(jsonl(out/'decisions.jsonl'))
    actions=list(jsonl(out/'actions.jsonl'))
    by_id={d['decision_id']:d for d in decisions}
    interventions=json.loads((pack/'config/interventions.json').read_text())
    profiles={}
    for row in csv_rows(pack/'data/profiles_snapshot.csv'):
        profiles.setdefault(row['user_id'],[]).append(row)
    histories={}
    for path in (pack/'data/events.jsonl',pack/'replay/live_events.jsonl',pack/'replay/triggers.jsonl'):
        if path.exists():
            for event in jsonl(path):
                viewer=histories.setdefault(event['user_id'],{})
                previous=viewer.get(event['event_id'])
                if not previous or ts(event.get('deliver_at') or event['received_at'])<ts(previous.get('deliver_at') or previous['received_at']):
                    viewer[event['event_id']]=event
    errors=[]
    def require(value,label,identity):
        if not value:
            errors.append({'id':identity,'problem':label})
    require(len(decisions)==len(triggers),'decision_coverage','run')
    require(len({a['action_id'] for a in actions})==len(actions),'duplicate_action','run')
    require(len({d['trigger_event_id'] for d in decisions})==len(decisions),'duplicate_decision','run')
    for action in actions:
        identity=action['action_id']
        decision=by_id.get(action['decision_id'])
        require(decision is not None,'missing_decision',identity)
        require(arms.get(action['user_id'])=='agent','holdout_action',identity)
        trigger=triggers[action['trigger_event_id']]
        at=ts(action['published_at'])
        history=sorted((e for e in histories.get(action['user_id'],{}).values() if ts(e.get('deliver_at') or e['received_at'])<=at),key=lambda e:ts(e['received_at']))
        snapshot=max((p for p in profiles.get(action['user_id'],[]) if ts(p['snapshot_at'])<=at and ts(p['updated_at'])<=at),key=lambda p:p['updated_at'],default={})
        facts={}
        for name,column in (('dialect','preferred_dialect'),('language','preferred_language'),('push_consent','notifications_opt_in'),('whatsapp_consent','whatsapp_opt_in')):
            if column in snapshot:
                value=snapshot[column]=='true' if name.endswith('consent') else snapshot[column]
                facts[name]={'value':value,'age_s':max(0,(at-ts(snapshot['updated_at'])).total_seconds())}
        for event in history:
            _,lag=event_time(event)
            if 0<=lag<=600 and event.get('app_dialect') and (at-ts(event['received_at'])).total_seconds()<=86400:
                facts['dialect']={'value':event['app_dialect']}
                if event.get('app_language'):
                    facts['language']={'value':event['app_language']}
            if event['event']=='notification_opt_out' and event['properties'].get('channel') in ('push','whatsapp'):
                facts[event['properties']['channel']+'_consent']={'value':False,'age_s':0}
        require(action['dialect']==facts.get('dialect',{}).get('value'),'wrong_dialect',identity)
        require(at>=ts(trigger['deliver_at']),'publication_before_trigger',identity)
        if decision:
            expected=ts(trigger['deliver_at'])+timedelta(milliseconds=decision['decided_in_ms'])
            require(abs((at-expected).total_seconds())<=.001,'timing_mismatch',identity)
            require(decision['model_calls']<=8 and decision['tool_calls']<=20,'call_budget',identity)
            require(decision['decided_in_ms']<=60000,'late_publication',identity)
        if action['type'] in MESSAGE_CHANNELS:
            def available(title,when):
                return bool(title and ts(title['available_from'])<=when and (not title['available_until'] or when<ts(title['available_until']))
                    and (title['title_id'] not in withdrawn or when<withdrawn[title['title_id']]))
            earlier=[a for a in actions if a['user_id']==action['user_id'] and a['action_id']!=identity
                and ts(a['published_at'])<=at]
            message_errors=verify_message(action,{'facts':facts},at,catalogue,available,interventions,earlier,history)
            for error in message_errors:
                require(False,error,identity)
            continue
        require(action['type']=='home_page','unsupported_channel',identity)
        rows=action.get('rows',[])
        require(1<=len(rows)<=6,'row_count',identity)
        ids=[action['hero_title_id']]
        for row in rows:
            require(3<=len(row['title_ids'])<=10,'row_size',identity)
            require(row['row_type'] in {'next_episode','because_you_watched','popular_in_dialect','new_releases','genre'},'row_type',identity)
            ids.extend(row['title_ids'])
        slugs=[]
        for tid in ids:
            title=catalogue.get(tid)
            require(title is not None,'unknown_title',identity)
            if title:
                require(title['dialect']==action['dialect'],'content_dialect',identity)
                require(ts(title['available_from'])<=at and (not title['available_until'] or at<ts(title['available_until'])),'unavailable_content',identity)
                require(tid not in withdrawn or at<withdrawn[tid],'withdrawn_content',identity)
                slugs.append(title['content_slug'])
        require(len(slugs)==len(set(slugs)),'repeated_content_slug',identity)
    fault_rows=[]
    by_trigger={d['trigger_event_id']:d for d in decisions}
    for fault in jsonl(pack/'replay/model_faults.jsonl'):
        d=by_trigger.get(fault['trigger_event_id'])
        if d is None:
            continue
        fault_rows.append({'trigger_event_id':fault['trigger_event_id'],'fault':fault['fault'],
            'model_called':bool(d['model_calls']),'outcome':d.get('model_fallback',d['reason']),
            'note':'Injection bypassed because no model call was needed' if not d['model_calls'] else 'Injected provider response checked'})
    report={'unique_trigger_count':len(triggers),'decision_count':len(decisions),'action_count':len(actions),
        'violations':errors,'violation_count':len(errors),'fault_coverage':fault_rows,
        'scope':'Independent static replay audit; does not establish production load capacity or provider privacy.'}
    write_json(report_path or out/'verification_report.json',report)
    return report
