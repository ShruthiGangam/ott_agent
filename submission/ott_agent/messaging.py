"""Deterministic message construction and separate channel policy checks."""
import re
from .common import IST, day, ts

MESSAGE_CHANNELS={'push','whatsapp','in_app_message'}

def quiet(now):
    return now.astimezone(IST).hour>=22 or now.astimezone(IST).hour<8

def make_message(channel, title, state, now, interventions):
    action={'type':channel,'dialect':title['dialect'],'title_id':title['title_id'],
        'send_at':now.isoformat(),'deeplink':'ott://title/'+title['title_id']}
    language=state['facts'].get('language',{}).get('value')
    if channel=='whatsapp':
        template=next((t for t in interventions['whatsapp']['approved_templates']
            if t['template_id']=='wa_recommend_title_v1' and t['language']==language),None)
        if not template:
            return None
        action.update(template_id=template['template_id'],variables={
            'title_name':title['title'],'dialect_name':title['dialect']})
    else:
        if language not in ('en','hin'):
            return None
        action['text']={'title':title['title'][:40],
            'body':('Watch '+title['title']+'.' if language=='en' else title['title']+' ab dekhiye.')[:120]}
    return action

def verify_message(action, state, now, catalogue, available, interventions, actions, history):
    """Does not call the planner, model or its channel-selection routine."""
    errors=[]
    channel=action.get('type')
    if channel not in MESSAGE_CHANNELS:
        return ['unsupported_action_channel']
    when=ts(action.get('send_at')) or now
    if abs((when-now).total_seconds())>2:
        errors.append('message_requires_dispatch_time_validation')
    title=catalogue.get(action.get('title_id'))
    dialect=state['facts'].get('dialect',{}).get('value')
    if not title or not available(title,when) or title['dialect']!=dialect or action.get('dialect')!=dialect:
        errors.append('invalid_content')
    if action.get('deeplink')!='ott://title/'+str(action.get('title_id')):
        errors.append('invalid_deeplink')
    if channel in ('push','whatsapp'):
        fact=state['facts'].get(channel+'_consent',{})
        if fact.get('value') is not True or fact.get('age_s',1e10)>7*86400:
            errors.append('missing_or_stale_consent')
        if quiet(when):
            errors.append('quiet_hours')
        previous=[a for a in actions if a.get('type') in ('push','whatsapp')]
        observed=[e for e in history if e['event'] in ('message_delivered','message_sent') and e.get('properties',{}).get('channel') in ('push','whatsapp')]
    else:
        previous=[a for a in actions if a.get('type')==channel]
        observed=[]
    if any(day(ts(a.get('send_at') or a['published_at']))==day(when) for a in previous):
        errors.append('frequency_cap')
    if any(day(ts(e['received_at']))==day(when) for e in observed):
        errors.append('frequency_cap')
    if channel=='whatsapp':
        template=next((t for t in interventions['whatsapp']['approved_templates'] if t['template_id']==action.get('template_id')),None)
        if not template or template['language']!=state['facts'].get('language',{}).get('value'):
            errors.append('unapproved_template_or_language')
        elif set(action.get('variables',{}))!=set(template['variables']):
            errors.append('invalid_template_variables')
        elif action['template_id']!='wa_recommend_title_v1' or action['variables']!={'title_name':title['title'] if title else None,'dialect_name':dialect}:
            errors.append('unsupported_or_invented_template_variables')
    else:
        text=action.get('text',{})
        if set(text)!={'title','body'} or not all(isinstance(x,str) for x in text.values()):
            errors.append('invalid_copy')
        else:
            combined=text['title']+' '+text['body']
            copy=interventions['push']['copy']
            if len(text['title'])>copy['title_max_chars'] or len(text['body'])>copy['body_max_chars']:
                errors.append('copy_length')
            if any(s in combined.lower() for s in copy['forbidden_phrases']) or re.search(r'\b(?:rs|inr)\b|[\u20b9$]|\b\d+\b',combined,re.I):
                errors.append('unsupported_copy_claim')
            # Only exact catalogue-derived copy is accepted; no model-generated text.
            expected=make_message(channel,title,state,now,interventions) if title else None
            if not expected or text!=expected['text']:
                errors.append('unapproved_copy')
    return sorted(set(errors))
