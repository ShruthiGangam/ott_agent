"""Durable dispatch boundary. Platform acceptance is not viewer delivery."""
import hashlib
import json
import sqlite3
from .common import iso, ts

class LocalPlatform:
    """Persistent local receiving backend for review before deployment.

    Requests are genuinely stored idempotently, but no phone is contacted. The
    supplied outcome simulator remains the source of delivery/viewer events.
    """
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS accepted(action_id TEXT PRIMARY KEY,digest TEXT,receipt TEXT)')
    def submit(self,action):
        digest=hashlib.sha256(json.dumps(action,sort_keys=True).encode()).hexdigest()
        row=self.db.execute('SELECT digest,receipt FROM accepted WHERE action_id=?',(action['action_id'],)).fetchone()
        if row:
            if row[0]!=digest:
                raise ValueError('idempotency_payload_conflict')
            return json.loads(row[1])
        receipt={'action_id':action['action_id'],'status':'accepted','backend':'local_platform',
            'delivered':False,'idempotency_key':action['action_id']}
        with self.db:
            self.db.execute('INSERT INTO accepted VALUES(?,?,?)',(action['action_id'],digest,json.dumps(receipt)))
        return receipt

def dispatch(agent,platform,now):
    store=agent.store
    report={'accepted':0,'cancelled':0,'failed':0,'delivered':0}
    rows=list(store.db.execute("SELECT action_id,user_id,body FROM outbox WHERE status='pending' ORDER BY rowid"))
    for aid,uid,body in rows:
        action=json.loads(body)
        if ts(action.get('send_at') or action['published_at'])>now:
            continue
        state=agent.evidence(uid,now)
        goal=next((g for g in store.goals(uid,open_only=True) if g['id']==action.get('goal_instance_id')),None)
        errors=[] if goal else ['goal_not_active']
        # The already-reserved action must not count against itself.
        if goal:
            if action['type']=='home_page':
                errors=agent.verify(state,goal['goal_id'],action,now,action['trigger_event_id'])
            else:
                from .messaging import verify_message
                errors=verify_message(dict(action,send_at=iso(now)),state,now,agent.catalogue,agent.available,
                    agent.interventions,[a for a in store.actions(uid) if a['action_id']!=aid],state['history'])
                if agent.arms.get(uid)!='agent':
                    errors.append('holdout')
                if goal['goal_id'] not in agent.allowed_goals(state,now) or now>=ts(goal['deadline']):
                    errors.append('goal_not_eligible')
        if errors:
            status='cancelled'
            receipt={'reason_codes':errors}
        else:
            try:
                receipt=platform.submit(action)
                if receipt.get('status')!='accepted' or receipt.get('action_id')!=aid:
                    raise ValueError('invalid_acceptance_receipt')
                status='accepted'
            except (OSError,ValueError,sqlite3.Error) as error:
                # Keep pending for an idempotent retry; never echo adapter details.
                report['failed']+=1
                store.record(uid,iso(now),'dispatch_retry',{'action_id':aid,'error':type(error).__name__})
                continue
        with store.db:
            store.db.execute('UPDATE outbox SET status=? WHERE action_id=?',(status,aid))
            store.record(uid,iso(now),'dispatch',dict(receipt,action_id=aid))
        report[status]+=1
    return report
