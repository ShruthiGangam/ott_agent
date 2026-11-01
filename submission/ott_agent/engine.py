"""Per-viewer goal ownership, evidence assembly, planning and independent checks."""
import hashlib
import json
import re
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path
from .common import csv_rows, day, event_time, iso, ts
from .provider import Provider, ProviderError
from .prompts import PROMPT_VERSION, PROMPT_SHA256
from .messaging import MESSAGE_CHANNELS, make_message, quiet, verify_message
from .explanations import explain, planning_trace

class Agent:
    def __init__(self, pack, store, provider=None, max_model_calls=8, max_tool_calls=20, deadline_s=60):
        if not 0 <= max_model_calls <= 8 or not 1 <= max_tool_calls <= 20 or not 0 < deadline_s <= 60:
            raise ValueError('Budgets must fit assignment ceilings')
        self.pack, self.store = Path(pack), store
        self.provider = provider or Provider()
        self.max_model_calls, self.max_tool_calls, self.deadline_s = max_model_calls, max_tool_calls, deadline_s
        self.catalogue = {r['title_id']: r for r in csv_rows(self.pack / 'data/catalogue.csv')}
        self.episodes = {}
        episode_file=self.pack/'data/episodes.csv'
        if episode_file.exists():
            for row in csv_rows(episode_file):
                self.episodes.setdefault(row['content_slug'],[]).append((int(row['season']),int(row['episode']),row['episode_id']))
            for episodes in self.episodes.values():
                episodes.sort()
        self.profiles = {}
        for n, row in enumerate(csv_rows(self.pack / 'data/profiles_snapshot.csv'), 2):
            row['_ref'] = 'profiles_snapshot.csv:line:' + str(n)
            self.profiles.setdefault(row['user_id'], []).append(row)
        self.arms = {r['user_id']: r['arm'] for r in csv_rows(self.pack / 'replay/arms.csv')}
        self.rules = {r['goal_id']: r for r in json.loads((self.pack / 'config/goals.json').read_text())['goals']}
        self.interpretations=json.loads((Path(__file__).resolve().parent/'assets/goal_interpretations.json').read_text())
        for gid in ('G06','G10'):
            if gid in self.rules:
                self.rules[gid]['interpretation']=self.interpretations[gid]
        if 'G10' in self.rules and self.interpretations['G10'].get('success'):
            self.rules['G10']['success']=dict(self.interpretations['G10']['success'])
            self.rules['G10']['version']='2026-10-31'
        self.prices = {r['plan_id']: r for r in json.loads((self.pack / 'config/pricing.json').read_text())['plans']}
        self.interventions = json.loads((self.pack / 'config/interventions.json').read_text())
        row = store.db.execute('SELECT MIN(received_at) FROM events').fetchone()
        self.coverage_start = ts(row[0]) if row and row[0] else None
        self.dependencies = {}
        self.withdrawn = {}
        # Replay durable control state after a process restart.
        for control in store.export_rows('controls'):
            self._apply_control(control, persist=False)

    def available(self, title, now):
        return bool(title and ts(title['available_from']) <= now
            and (not title['available_until'] or now < ts(title['available_until']))
            and (title['title_id'] not in self.withdrawn or now < ts(self.withdrawn[title['title_id']])))

    def evidence(self, user_id, now):
        history = self.store.history(user_id, iso(now))
        profiles = [p for p in self.profiles.get(user_id, []) if ts(p['snapshot_at']) <= now and ts(p['updated_at']) <= now]
        profile = max(profiles, key=lambda p: (p['updated_at'], p['_ref'])) if profiles else {}
        facts, conflicts = {}, []
        def fact(name, value, source, at):
            facts[name] = {'value': value, 'source': source, 'as_of': iso(at),
                           'age_s': round(max(0, (now-at).total_seconds()), 3)}
        if profile:
            for name, value in (('subscription_status', profile['subscription_status']),
                                ('signup_at', profile['signup_at']), ('dialect', profile['preferred_dialect']),
                                ('language', profile['preferred_language']),
                                ('push_consent', profile['notifications_opt_in'] == 'true'),
                                ('whatsapp_consent', profile['whatsapp_opt_in'] == 'true')):
                fact(name, value, profile['_ref'], ts(profile['updated_at']))
        billing = []
        genres = Counter()
        signup_seen = False
        for event in history:
            when, lag = event_time(event)
            name, props = event['event'], event.get('properties', {})
            ref = 'event:' + event['event_id']
            if name == 'signup_completed':
                signup_seen = True
                if 'signup_at' not in facts:
                    fact('signup_at', iso(when), ref, when)
            if 0 <= lag <= 600 and event.get('app_dialect') and (now-ts(event['received_at'])).total_seconds()<=86400:
                campaign=props.get('campaign_dialect')
                link=props.get('deeplink')
                match=re.fullmatch(r'ott://c/[^/]{1,100}/(d[1-6])/title/[A-Za-z0-9_-]{1,100}',link) if isinstance(link,str) else None
                campaign=match.group(1) if match else campaign
                if campaign in ('d1','d2','d3','d4','d5','d6') and campaign!=event['app_dialect']:
                    conflicts.append({'field':'dialect','rejected':{'value':campaign,'source':ref+':campaign_link'},
                        'resolved_by':ref,'reason':'Campaign dialect is a navigation hint; current app settings determine display'})
                if 'dialect' in facts and facts['dialect']['value'] != event['app_dialect']:
                    conflicts.append({'field': 'dialect', 'rejected': facts['dialect'], 'resolved_by': ref,
                                      'reason': 'fresh app setting determines what the app displays'})
                fact('dialect', event['app_dialect'], ref, ts(event['received_at']))
                if event.get('app_language'):
                    fact('language', event['app_language'], ref, ts(event['received_at']))
            if name == 'notification_opt_out':
                channel = props.get('channel')
                if channel in ('push', 'whatsapp'):
                    fact(channel + '_consent', False, ref, ts(event['received_at']))
            if name in ('purchase_completed', 'subscription_renewed', 'subscription_lapsed'):
                billing.append((when, event))
            if name == 'play_started':
                title = self.catalogue.get(props.get('title_id'))
                if title:
                    genres.update(title['genres'].split('|'))
        ever_paid = any(e['event'] == 'subscription_renewed' or
            (e['event'] == 'purchase_completed' and e['properties'].get('is_trial') is False) for _, e in billing)
        if billing:
            when, event = max(billing, key=lambda pair: (pair[0], pair[1]['received_at']))
            old = facts.get('subscription_status')
            if not old or when >= ts(old['as_of']) or (ever_paid and old['value'] == 'never'):
                props = event.get('properties', {})
                status = ('lapsed' if event['event'] == 'subscription_lapsed' else
                          'trial_active' if props.get('is_trial') is True else 'active')
                if old and old['value'] != status:
                    conflicts.append({'field': 'subscription_status', 'rejected': old,
                        'resolved_by': 'event:' + event['event_id'], 'reason': 'billing event overrides stale or contradicted warehouse status'})
                fact('subscription_status', status, 'event:' + event['event_id'], when)
                plan = self.prices.get(props.get('plan_id'))
                if plan:
                    fact('plan_ends_at', iso(when + timedelta(days=plan['days'])), 'event:' + event['event_id'], when)
        if 'plan_ends_at' not in facts and profile.get('plan_ends_at'):
            fact('plan_ends_at', profile['plan_ends_at'], profile['_ref'], ts(profile['updated_at']))
        lapses=[(when,e) for when,e in billing if e['event']=='subscription_lapsed']
        if lapses:
            when,e=max(lapses,key=lambda item:item[0])
            fact('lapsed_at',iso(when),'event:'+e['event_id'],when)
        elif facts.get('subscription_status',{}).get('value')=='lapsed' and facts.get('plan_ends_at'):
            end=ts(facts['plan_ends_at']['value'])
            if end and end<=now:
                fact('lapsed_at',iso(end),facts['plan_ends_at']['source'],end)
        current = facts.get('subscription_status')
        if current and current['value'] in ('active', 'trial_active'):
            end = facts.get('plan_ends_at', {}).get('value')
            if not end or ts(end) <= now:
                conflicts.append({'field': 'subscription_status', 'rejected': current,
                    'reason': 'plan end missing or passed; current entitlement is uncertain'})
                fact('subscription_status', 'unknown', 'derived:entitlement_uncertain', now)
        return {'user_id': user_id, 'facts': facts, 'conflicts': conflicts[-12:], 'history': history,
                'signup_seen': signup_seen, 'ever_paid': ever_paid, 'genres': dict(genres)}

    def resume_target(self, state, now):
        signup=ts(state['facts'].get('signup_at',{}).get('value'))
        if not (signup and self.coverage_start and signup>=self.coverage_start and state['signup_seen']):
            return None
        watched={}
        latest={}
        for event in state['history']:
            if event['event'] not in ('play_started','episode_completed'):
                continue
            title=self.catalogue.get(event.get('properties',{}).get('title_id'))
            if not title or title['content_type'] not in ('show','micro_drama'):
                continue
            slug=title['content_slug']
            watched.setdefault(slug,set()).add(event['properties'].get('episode_id'))
            if event['event']=='play_started':
                when,lag=event_time(event)
                if lag>=0 and (slug not in latest or when>latest[slug][0]):
                    latest[slug]=(when,event['event_id'])
        dialect=state['facts'].get('dialect',{}).get('value')
        for slug,(last,ref) in sorted(latest.items(),key=lambda pair:pair[1][0],reverse=True):
            remaining=[ep[2] for ep in self.episodes.get(slug,[]) if ep[2] not in watched[slug]]
            if now-last>=timedelta(days=3) and remaining and any(t['content_slug']==slug and t['dialect']==dialect and self.available(t,now) for t in self.catalogue.values()):
                return {'content_slug':slug,'last_play_at':iso(last),'next_episode_id':remaining[0],
                    'remaining_episode_count':len(remaining),'evidence':'event:'+ref}
        return None

    def candidates(self, state, now, trigger_id=None):
        facts, history = state['facts'], state['history']
        status = facts.get('subscription_status', {}).get('value', 'unknown')
        signup = ts(facts.get('signup_at', {}).get('value'))
        age = (now-signup).total_seconds()/86400 if signup else None
        complete_history = bool(signup and self.coverage_start and signup >= self.coverage_start and state['signup_seen'])
        plays = [e for e in history if e['event'] == 'play_started']
        completed = [e for e in history if e['event'] == 'episode_completed']
        goals = []
        if complete_history and 0 <= age <= 7 and not plays:
            goals.append('G01')
        if complete_history and not completed:
            goals.append('G02')
        if age is not None and 0 <= age <= 2:
            goals.append('G03')
        if status == 'trial_active':
            goals.append('G04')
        if status == 'never' and not state['ever_paid']:
            goals.append('G05')
        lapse=ts(facts.get('lapsed_at',{}).get('value'))
        if status=='lapsed' and lapse and 0<=(now-lapse).total_seconds()<=self.interpretations['G06']['recently_lapsed_days']*86400:
            goals.append('G06')
        if self.resume_target(state,now):
            goals.append('G07')
        if status == 'active':
            goals.append('G11')
            recent_days = {day(event_time(e)[0]) for e in plays if now-timedelta(days=14) <= event_time(e)[0] < now}
            if self.coverage_start and self.coverage_start <= now-timedelta(days=14) and len(recent_days) <= 1:
                goals.append('G09')
            dialect = facts.get('dialect', {}).get('value')
            if any(t['dialect'] == dialect and self.available(t, now)
                   and 0 <= (day(now)-ts(t['release_date']).date()).days <= 30 for t in self.catalogue.values()):
                goals.append('G08')
        previous_opens = [e for e in history if e['event'] == 'app_open' and e['event_id'] != trigger_id
                          and now-timedelta(days=14) <= event_time(e)[0] < now]
        known_old_viewer=bool((signup and signup<=now-timedelta(days=14)) or any(ts(e['received_at'])<=now-timedelta(days=14) for e in history))
        if self.coverage_start and self.coverage_start <= now-timedelta(days=14) and known_old_viewer and not previous_opens:
            goals.append('G12')
        if self.rules.get('G10',{}).get('success',{}).get('event'):
            goals.append('G10')
        return [g for g in goals if g in self.rules]

    def allowed_goals(self, state, now, trigger_id=None):
        goals = self.candidates(state, now, trigger_id)
        status = state['facts'].get('subscription_status', {}).get('value')
        for active in self.store.goals(state['user_id'], open_only=True):
            gid = active['goal_id']
            compatible = (gid not in ('G04', 'G05', 'G06', 'G08', 'G09','G11') or
                (gid == 'G04' and status == 'trial_active') or
                (gid == 'G05' and status == 'never' and not state['ever_paid']) or
                (gid=='G06' and status=='lapsed') or
                (gid in ('G08', 'G09','G11') and status == 'active'))
            # Entry eligibility is frozen at commitment; merely opening again or
            # aging past a signup threshold must not invalidate an ongoing goal.
            if compatible and now < ts(active['deadline']) and gid not in goals:
                goals.insert(0, gid)
        return goals

    def _apply_control(self, control, persist=True):
        key = hashlib.sha256(json.dumps(control, sort_keys=True).encode()).hexdigest()
        if persist and self.store.db.execute('SELECT 1 FROM controls WHERE id=?', (key,)).fetchone():
            return
        kind = control['type']
        if kind == 'title_withdrawn':
            self.withdrawn[control['title_id']] = control['at']
        elif kind == 'goal_rule_corrected':
            rule = control['goal_id']
            self.rules[rule]['success'].update(control['new_success'])
            self.rules[rule]['version'] = control['at']
            if persist:
                for goal in self.store.goals(open_only=True, rule=rule):
                    goal['success'].update(control['new_success'])
                    goal['rule_version'] = control['at']
                    goal['revised_at']=control['at']
                    goal.setdefault('revisions', []).append({'at': control['at'], 'reason': 'goal_rule_corrected'})
                    self.store.put_goal(goal)
                    state=self.store.state(goal['user_id'])
                    if state:
                        state.update(active_goal=goal,needs_replan=True)
                        self.store.save_state(goal['user_id'],state)
                        self.store.record(goal['user_id'],control['at'],'rule_revision',{'goal_id':goal['id'],'success':goal['success']})
        elif kind in ('dependency_unavailable', 'dependency_degraded'):
            self.dependencies[control['dependency']] = control
        if persist:
            key = hashlib.sha256(json.dumps(control, sort_keys=True).encode()).hexdigest()
            self.store.db.execute('INSERT OR IGNORE INTO controls VALUES(?,?)', (key, json.dumps(control)))

    def dependency(self, name, now):
        control = self.dependencies.get(name)
        return control if control and ts(control['at']) <= now < ts(control['until']) else None

    def matches(self, goal, event):
        when, lag = event_time(event)
        start, end = ts(goal['started_at']), ts(goal['deadline'])
        if lag < 0 or not start <= when <= end or ts(event['received_at']) < start:
            return False
        gid, props = goal['goal_id'], event.get('properties', {})
        if event['event'] != goal['success']['event']:
            return False
        if gid in ('G04', 'G05','G06'):
            return props.get('is_trial') is False
        if gid == 'G07':
            title=self.catalogue.get(props.get('title_id'))
            return bool(title and title['content_slug']==goal.get('target_content_slug'))
        if gid == 'G03':
            return day(when) > day(start)
        if gid == 'G08':
            title = self.catalogue.get(props.get('title_id'))
            return bool(title and 0 <= (day(start)-ts(title['release_date']).date()).days <= 30)
        return True

    def reconcile(self, user_id, now, complete_observation=False):
        for goal in self.store.goals(user_id):
            if goal['status'] not in ('open','inconclusive') or goal.get('invalidated_at'):
                continue
            matches = [e for e in self.store.history(user_id, iso(now)) if self.matches(goal, e)]
            enough = len({day(event_time(e)[0]) for e in matches}) >= 3 if goal['goal_id'] == 'G09' else bool(matches)
            if enough:
                goal.update(status='succeeded', judged_at=iso(now), evidence=['event:' + e['event_id'] for e in matches],
                            causal_claim=False, reason='Observed success signal inside committed goal window')
            elif now >= ts(goal['deadline']):
                observable=complete_observation and goal['goal_id']!='G11'
                goal.update(status='failed' if observable else 'inconclusive', judged_at=iso(now), evidence=[],
                    causal_claim=False, reason='No qualifying signal; complete simulator horizon' if observable else 'Deadline passed; telemetry completeness not established')
            self.store.put_goal(goal)

    def observe(self, event, now):
        if not self.store.add_event(event):
            return
        uid=event['user_id']
        self.store.record(uid,iso(now),'observation',{'event_id':event['event_id'],'event':event['event']})
        self.reconcile(uid,now)
        previous=self.store.state(uid)
        if previous is None:
            return
        fresh=self.evidence(uid,now)
        eligible=self.allowed_goals(fresh,now)
        for goal in self.store.goals(uid,open_only=True):
            if goal['goal_id'] not in eligible:
                goal.update(status='inconclusive',invalidated_at=iso(now),judged_at=iso(now),
                    reason='New observed facts invalidate the active plan',causal_claim=False)
                self.store.put_goal(goal)
        active=self.store.goals(uid,open_only=True)
        if not active:
            self.store.cancel_plan(uid,iso(now),'Goal closed or invalidated by observed event')
        outcomes=self.store.goals(uid)
        previous.update({k:v for k,v in fresh.items() if k!='history'})
        previous.update(active_goal=active[0] if active else None,goal_outcomes=outcomes,
            needs_replan=not bool(active),last_observation='event:'+event['event_id'])
        if not active:
            previous['active_plan']=None
        previous['learning']={'observed_successes':sum(g['status']=='succeeded' for g in outcomes),
            'reason':'Goal signals update local history; individual causation is not assumed','as_of':iso(now)}
        self.store.save_state(uid,previous)
        self.store.record(uid,iso(now),'viewer_state',previous)

    def tick(self,now):
        """Deadline event; missing telemetry remains inconclusive."""
        for uid in {g['user_id'] for g in self.store.goals(open_only=True)}:
            self.reconcile(uid,now)
            state=self.store.state(uid)
            if state:
                active=self.store.goals(uid,open_only=True)
                state.update(active_goal=active[0] if active else None,goal_outcomes=self.store.goals(uid),needs_replan=not bool(active))
                plan=state.get('active_plan') or {}
                expired=plan.get('type')=='home_page' and ts(plan['published_at'])+timedelta(minutes=self.interventions['home_page'].get('ttl_minutes',120))<=now
                if not active or expired:
                    state['active_plan']=None
                    state['needs_replan']=True
                    self.store.cancel_plan(uid,iso(now),'Page TTL expired' if expired else 'Deadline reached without complete attributable telemetry')
                self.store.save_state(uid,state)
                self.store.record(uid,iso(now),'deadline_review',state)

    def channel_options(self,state,goals,now,trigger_id=None,prefer_outbound=False):
        channels=['home_page']
        opens=[event_time(e)[0] for e in state['history'] if e['event']=='app_open' and e['event_id']!=trigger_id]
        returning=not opens or now-max(opens)>=timedelta(days=3)
        if not returning or not any(g in ('G06','G07','G12') for g in goals):
            return channels
        for channel in ('push','whatsapp','in_app_message'):
            page=self.page(state,goals[0],now)
            title=self.catalogue.get(page['hero_title_id']) if page else None
            action=make_message(channel,title,state,now,self.interventions) if title else None
            if action and not verify_message(action,state,now,self.catalogue,self.available,self.interventions,
                    self.store.actions(state['user_id']),state['history']):
                channels.append(channel)
        return [channels[1]] if prefer_outbound and len(channels)>1 else channels

    def planning_context(self,state,choices,channels,active):
        evidence=[]
        for key in ('subscription_status','dialect','language','push_consent','whatsapp_consent'):
            fact=state['facts'].get(key)
            if not fact or fact['value'] is None:
                continue
            value=fact['value']
            if key=='language' and value not in ('en','hin'):
                value='unknown'
            evidence.append({'key':'F'+str(len(evidence)),'fact':key,'value':value,
                'freshness':'fresh' if fact['age_s']<600 else 'recent' if fact['age_s']<7*86400 else 'old'})
        return {'eligible_goals':[{'goal_id':g,'success_event':self.rules[g]['success']['event'],
            'window_hours':self.rules[g]['success']['window_hours'],'rule_version':self.rules[g].get('version','2026-09-30')} for g in choices],
            'evidence':evidence,'channel_options':channels,'active_goal_id':active[0]['goal_id'] if active else None,
            'activity':{'plays':min(10,sum(e['event']=='play_started' for e in state['history'])),
            'completions':min(10,sum(e['event']=='episode_completed' for e in state['history']))}}

    def page(self, state, goal_id, now):
        dialect = state['facts'].get('dialect', {}).get('value')
        genres = state['genres']
        titles = [t for t in self.catalogue.values() if t['dialect'] == dialect and self.available(t, now)]
        def score(title):
            recent = 0 <= (day(now)-ts(title['release_date']).date()).days <= 30
            taste = sum(genres.get(g, 0) for g in title['genres'].split('|'))
            return (recent if goal_id == 'G08' else False, taste, title['release_date'], title['title_id'])
        titles.sort(key=score, reverse=True)
        if goal_id=='G07':
            target=self.resume_target(state,now)
            if target:
                titles.sort(key=lambda t:t['content_slug']!=target['content_slug'])
        unique, seen = [], set()
        for title in titles:
            if title['content_slug'] not in seen:
                seen.add(title['content_slug'])
                unique.append(title['title_id'])
        if len(unique) < 4:
            return None
        rows = []
        for start in range(1, min(len(unique), 16), 5):
            group = unique[start:start+5]
            if len(group) >= 3:
                recent_row = all(0 <= (day(now)-ts(self.catalogue[t]['release_date']).date()).days <= 30 for t in group)
                rows.append({'row_type': 'new_releases' if goal_id == 'G08' and recent_row else 'genre', 'title_ids': group})
        return {'type': 'home_page', 'dialect': dialect, 'hero_title_id': unique[0], 'rows': rows}

    def verify(self, state, goal_id, action, now, trigger_id):
        errors = []
        if self.arms.get(state['user_id']) != 'agent':
            errors.append('holdout_or_unknown_arm')
        if goal_id not in self.allowed_goals(state, now, trigger_id):
            errors.append('ineligible_goal')
        if action.get('type') in MESSAGE_CHANNELS:
            errors.extend(verify_message(action,state,now,self.catalogue,self.available,self.interventions,
                self.store.actions(state['user_id']),state['history']))
            if goal_id not in ('G06','G07','G12'):
                errors.append('message_without_reminder_goal')
            return sorted(set(errors))
        if action.get('type')!='home_page':
            return errors+['unsupported_action_channel']
        if action.get('dialect') != state['facts'].get('dialect', {}).get('value'):
            errors.append('wrong_dialect')
        policy = self.interventions['home_page']['rows']
        if not action.get('rows') or len(action['rows']) > policy['max_rows']:
            errors.append('invalid_row_count')
        ids = [action.get('hero_title_id')]
        for row in action.get('rows', []):
            if row['row_type'] not in policy['row_types'] or not policy['min_titles_per_row'] <= len(row['title_ids']) <= policy['max_titles_per_row']:
                errors.append('invalid_row')
            ids.extend(row['title_ids'])
        seen = set()
        for title_id in ids:
            title = self.catalogue.get(title_id)
            if not self.available(title, now) or title['dialect'] != action.get('dialect'):
                errors.append('invalid_content')
            elif title['content_slug'] in seen:
                errors.append('duplicate_content')
            else:
                seen.add(title['content_slug'])
        return sorted(set(errors))

    def decide(self, trigger, fault=None, controls_until=None, queue_delay_s=0):
        started = time.perf_counter()-max(0,queue_delay_s)
        existing = self.store.decision(trigger['event_id'])
        if existing:
            return existing
        delivery=ts(trigger['deliver_at'])
        now = delivery+timedelta(seconds=max(0,queue_delay_s))
        uid, eid = trigger['user_id'], trigger['event_id']
        did = 'D-' + hashlib.sha256(eid.encode()).hexdigest()[:20]
        when, lag = event_time(trigger)
        age = max(0, (now-when).total_seconds())
        decision = {'decision_id': did, 'user_id': uid, 'trigger_event_id': eid,
            'trigger': {'event': trigger['event'], 'received_at': trigger['received_at'], 'deliver_at': trigger['deliver_at'], 'event_age_s': round(age, 3), 'queue_delay_ms':round(max(0,queue_delay_s)*1000,3)},
            'action': 'NO_ACTION', 'status': 'NO_ACTION', 'reason': '', 'goal': None, 'model_source': 'not_called', 'model_calls': 0, 'tool_calls': 0,
            'checks': {'passed': [], 'failed': [], 'not_applicable':['outbound_consent','outbound_frequency_cap','message_quiet_hours']}, 'assumptions': [], 'confidence': {'value': 0, 'reason': 'No supported plan yet'}}
        decision.update(prompt_version=PROMPT_VERSION,prompt_sha256=PROMPT_SHA256)
        decision['provider_mode']=getattr(self.provider,'mode','live')
        decision['planning']={'assigned_arm':self.arms.get(uid,'unknown'),
            'trigger_lag_s':lag,'fresh_evidence_read':False}
        previous_state=self.store.state(uid) or {'user_id':uid,'facts':{},'conflicts':[]}
        state, action = dict(previous_state), None
        reason = None
        if queue_delay_s>=self.deadline_s:
            reason='queue_deadline_exceeded'
        elif lag < 0 or age > 600:
            reason = 'late_or_ambiguous_trigger'
        elif trigger.get('app_dialect') not in {t['dialect'] for t in self.catalogue.values()}:
            reason = 'missing_current_app_dialect'
        dep = self.dependency('user_data_store', now)
        if not reason and dep:
            # Deterministic fault schedule: one read in five times out, remaining reads take 8 seconds.
            if int(hashlib.sha256(eid.encode()).hexdigest()[:8], 16) % 5 == 0:
                time.sleep(min(0.05, self.deadline_s))
                reason = 'user_data_store_timeout'
            elif self.deadline_s-(time.perf_counter()-started) <= 8:
                reason = 'insufficient_budget_for_degraded_store'
            else:
                time.sleep(8)
                decision['dependency_read_ms'] = 8000
        if not reason:
            self.reconcile(uid, now)
            state = self.evidence(uid, now)
            decision['tool_calls'] += 1
            eligible = self.allowed_goals(state, now, eid)
            active = self.store.goals(uid, open_only=True)
            if active and active[0]['goal_id'] not in eligible:
                old = active[0]
                old.update(status='inconclusive', invalidated_at=iso(now), judged_at=iso(now), reason='Situation changed; plan invalidated', causal_claim=False)
                self.store.put_goal(old)
                active = []
            choices = [active[0]['goal_id']] if active else eligible
            decision['planning'].update(planning_trace(state,choices,active,now,eid,self.coverage_start,
                self.resume_target(state,now) if 'G07' in choices else None))
            latest_page=self.store.latest_action(uid)
            live_page=bool(active and latest_page and latest_page.get('type')=='home_page' and latest_page.get('goal_instance_id')==active[0]['id']
                and latest_page.get('dialect')==state['facts'].get('dialect',{}).get('value')
                and ts(latest_page['published_at'])<=now<ts(latest_page['published_at'])+timedelta(minutes=self.interventions['home_page'].get('ttl_minutes',120))
                and all(self.available(self.catalogue.get(t),now) for t in [latest_page.get('hero_title_id')]+[tid for row in latest_page.get('rows',[]) for tid in row['title_ids']]))
            if live_page:
                decision['goal']=active[0]
                reason='current_plan_still_live'
            elif not choices:
                reason = 'no_measurable_eligible_goal'
            elif self.max_tool_calls < 2:
                reason = 'insufficient_tool_budget_for_verification'
            else:
                chosen = choices[0]
                channel='home_page'
                proposed_no_action=False
                channels=self.channel_options(state,choices,now,eid,prefer_outbound=trigger['event']=='lifecycle_replan')
                context=self.planning_context(state,choices,channels,active)
                decision['model_input']=context
                decision['confidence'] = {'value': 0.6, 'reason': 'Deterministic eligibility evidence; not a calibrated probability'}
                if self.arms.get(uid) == 'agent' and self.max_model_calls and time.perf_counter()-started < self.deadline_s-self.provider.timeout:
                    decision['model_calls'] = 1
                    try:
                        kwargs={'fault':fault,'unavailable':bool(self.dependency('model_provider',now))}
                        if hasattr(self.provider,'primary'):
                            kwargs['max_attempts']=min(2,self.max_model_calls)
                        proposal = self.provider.plan(context,**kwargs)
                        chosen = proposal['goal_id'] or chosen
                        channel=proposal['intervention']
                        proposed_no_action=channel=='no_action'
                        decision['model_proposal']=proposal
                        decision['model_confidence'] = proposal['confidence']
                        attempts=getattr(self.provider,'last_attempts',[])
                        used_secondary=bool(attempts and hasattr(self.provider,'secondary') and self.provider.secondary
                            and attempts[-1]['model']==self.provider.secondary.config[2])
                        decision['model_source'] = ('recorded_llm' if getattr(self.provider,'mode','live')=='recorded' else
                            'live_llm_cache' if getattr(self.provider,'last_request_cached',False) else
                            'live_llm_fallback' if used_secondary else 'injected_fault' if fault else 'live_llm')
                        decision['model_name'] = self.provider.last_response_model
                        decision['model_usage'] = dict(self.provider.last_usage)
                        attempts=getattr(self.provider,'last_attempts',[])
                        decision['model_attempts']=list(attempts)
                        decision['model_calls']=max(1,len(attempts))
                        decision['network_model_calls']=sum(a['network'] for a in attempts) if attempts else int(getattr(self.provider,'last_network_request',False))
                    except ProviderError as error:
                        decision['model_fallback'] = str(error)
                        decision['model_source'] = 'verified_fallback'
                        decision['network_model_calls']=int(getattr(self.provider,'last_network_request',False))
                        decision['model_usage']=dict(self.provider.last_usage)
                        attempts=getattr(self.provider,'last_attempts',[])
                        decision['model_attempts']=list(attempts)
                        decision['model_calls']=max(1,len(attempts))
                        decision['network_model_calls']=sum(a['network'] for a in attempts) if attempts else int(getattr(self.provider,'last_network_request',False))
                action = None if proposed_no_action else self.page(state, chosen, now)
                if action and channel in MESSAGE_CHANNELS:
                    title=self.catalogue[action['hero_title_id']]
                    action=make_message(channel,title,state,now,self.interventions)
                if proposed_no_action:
                    reason='model_insufficient_evidence' if proposal['reason_code']=='insufficient_evidence' else 'model_chose_no_action'
                if self.arms.get(uid) != 'agent':
                    reason, action = 'holdout_or_unknown_arm', None
                elif action is None and not proposed_no_action:
                    reason = 'insufficient_valid_content'
                # Revalidate using independently read evidence at actual publication time.
                published = delivery + timedelta(seconds=time.perf_counter()-started)
                if controls_until:
                    controls_until(published)
                fresh = self.evidence(uid, published)
                decision['tool_calls'] += 1
                if action and action['type'] in MESSAGE_CHANNELS:
                    action['send_at']=iso(published)
                errors = self.verify(fresh, chosen, action, published, eid) if action else []
                if errors:
                    decision['checks']['failed'] = errors
                    reason, action = 'verification_rejected', None
                if not active:
                    rule = self.rules[chosen]
                    goal = {'id': 'G-' + did[2:], 'user_id': uid, 'goal_id': chosen, 'status': 'open',
                        'started_at': iso(published), 'deadline': iso(published+timedelta(hours=rule['success']['window_hours'])),
                        'success': dict(rule['success']), 'rule_version': rule.get('version', '2026-09-30'),
                        'evidence': [v['source'] for v in fresh['facts'].values()], 'causal_claim': False,
                        'plan': {'action': action['type'] if action else 'observe', 'reason': 'Supported next step; revise on new evidence'}}
                    if 'interpretation' in rule:
                        goal['interpretation']=rule['interpretation']
                    if chosen=='G11':
                        goal['telemetry_completeness']='not_established_for_tv_app_open'
                    if chosen=='G07':
                        target=self.resume_target(fresh,published)
                        if target:
                            goal.update(target_content_slug=target['content_slug'],target_episode_id=target['next_episode_id'])
                            goal['evidence'].append(target['evidence'])
                    if chosen in self.candidates(fresh, published, eid):
                        self.store.put_goal(goal)
                    else:
                        goal = None
                else:
                    goal = active[0]
                decision['goal'] = goal
                state = fresh
        elapsed = time.perf_counter()-started
        if elapsed > self.deadline_s or decision['tool_calls'] > self.max_tool_calls:
            reason, action = 'decision_budget_exceeded', None
        if action and decision['tool_calls'] + 1 > self.max_tool_calls:
            reason, action = 'decision_budget_exceeded', None
        if action:
            decision['tool_calls'] += 1
            published = delivery + timedelta(seconds=time.perf_counter()-started)
            if controls_until:
                controls_until(published)
            final_state = self.evidence(uid, published)
            latest = next((g for g in self.store.goals(uid) if g['id'] == decision['goal']['id']), decision['goal'])
            decision['goal'] = latest
            if action['type'] in MESSAGE_CHANNELS:
                action['send_at']=iso(published)
            final_errors = self.verify(final_state, decision['goal']['goal_id'], action, published, eid)
            if latest['status'] != 'open':
                final_errors.append('goal_closed_during_decision')
            if time.perf_counter()-started > self.deadline_s:
                final_errors.append('deadline_exceeded')
            if final_errors:
                action = None
                reason = 'publication_revalidation_rejected'
                decision['checks']['failed'] = final_errors
            else:
                state = final_state
        if action:
            published = delivery + timedelta(seconds=time.perf_counter()-started)
            action.update(action_id='A-' + did[2:], decision_id=did, user_id=uid,
                          trigger_event_id=eid, published_at=iso(published),goal_instance_id=decision['goal']['id'])
            decision.update(action=action['type'].upper(), status='PUBLISHED', reason='Verified goal-directed intervention')
            decision['checks']['passed'] = ['eligibility', 'dialect', 'availability', 'row_shape', 'content_slug_unique', 'holdout', 'idempotency']
            if action['type'] in MESSAGE_CHANNELS:
                action['send_at']=iso(published)
                decision['checks']['not_applicable']=[]
                decision['checks']['passed']=['eligibility','dialect','availability','consent','quiet_hours','shared_frequency_cap','copy_or_template','holdout','idempotency']
        else:
            decision['reason'] = reason or 'safe_abstention'
        decision['dialect'] = state['facts'].get('dialect')
        decision['conflicts'] = state['conflicts']
        decision['reason_code']='verified_intervention' if action else decision['reason']
        decision['explanation']=explain(decision,action)
        decision['final_reason']=decision['explanation']['summary']
        if action and time.perf_counter()-started > self.deadline_s:
            action=None
            decision.update(action='NO_ACTION',status='NO_ACTION',reason='decision_budget_exceeded',reason_code='decision_budget_exceeded')
            decision['checks']['failed'].append('deadline_exceeded')
            decision['explanation']=explain(decision)
            decision['final_reason']=decision['explanation']['summary']
        decision['decided_in_ms'] = round((time.perf_counter()-started)*1000, 3)
        decision['published_at'] = iso(delivery+timedelta(milliseconds=decision['decided_in_ms']))
        if action:
            action['published_at'] = decision['published_at']
        decision['dialect'] = state['facts'].get('dialect')
        decision['conflicts'] = state['conflicts']
        for fact in state['facts'].values():
            fact['age_s']=round(max(0,(ts(decision['published_at'])-ts(fact['as_of'])).total_seconds()),3)
        decision['evidence'] = list(state['facts'].values())
        decision['content'] = (([action['hero_title_id']] + [tid for r in action['rows'] for tid in r['title_ids']]) if action['type']=='home_page' else [action['title_id']]) if action else []
        decision['assumptions'] = ['Snapshot never-paid is a warehouse claim, checked against all observed billing events.',
            'Absence-based first-play/completion goals require observed signup inside pack coverage.',
            'Phone send-minus-occur duration is usable only when nonnegative; clock changes can still make it uncertain.']
        insufficient={'missing_current_app_dialect':['current_app_dialect'],
            'model_insufficient_evidence':['model_declined_supported_next_step'],
            'no_measurable_eligible_goal':['supported_goal_eligibility_and_success_signal'],
            'user_data_store_timeout':['fresh_viewer_state'],
            'insufficient_valid_content':['enough_available_titles_in_current_dialect']}
        if action:
            decision['decision_kind']='ACT'
        else:
            decision['decision_kind']='INSUFFICIENT_EVIDENCE' if decision['reason'] in insufficient else 'ABSTAIN'
            decision['no_action']={'valid_decision':True,'reason_code':decision['reason'],
                'missing_evidence':insufficient.get(decision['reason'],[]),
                'reconsider_on':'fresh relevant evidence, an eligible goal, or recovery within the decision budget'}
        decision['checks']['passed'].append('recorded_decision')
        saved=dict(previous_state)
        saved.update({k:v for k,v in state.items() if k!='history'})
        active_now=self.store.goals(uid,open_only=True)
        saved['active_goal'] = active_now[0] if active_now else None
        saved['active_plan']=action or (saved.get('active_plan') if active_now else None)
        saved['last_decision_id'] = did
        self.store.save_decision(decision, saved, action)
        return decision
