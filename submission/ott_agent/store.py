"""SQLite is authoritative; JSONL outputs are rebuildable exports."""
import json
import sqlite3
from .common import iso, ts
class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA busy_timeout=5000')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, user_id TEXT, received_at TEXT, body TEXT);
        CREATE INDEX IF NOT EXISTS events_user ON events(user_id, received_at);
        CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY, trigger_id TEXT UNIQUE, user_id TEXT, body TEXT);
        CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY, decision_id TEXT UNIQUE, body TEXT);
        CREATE TABLE IF NOT EXISTS goals(id TEXT PRIMARY KEY, user_id TEXT, goal_id TEXT, status TEXT, body TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS one_open_goal ON goals(user_id) WHERE status='open';
        CREATE INDEX IF NOT EXISTS goals_rule_status ON goals(goal_id, status);
        CREATE TABLE IF NOT EXISTS viewer_state(user_id TEXT PRIMARY KEY, body TEXT);
        CREATE TABLE IF NOT EXISTS controls(id TEXT PRIMARY KEY, body TEXT);
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS plans(user_id TEXT PRIMARY KEY, goal_id TEXT, action_id TEXT, status TEXT, body TEXT);
        CREATE TABLE IF NOT EXISTS outbox(action_id TEXT PRIMARY KEY, user_id TEXT, status TEXT, body TEXT);
        CREATE TABLE IF NOT EXISTS timeline(seq INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT,at TEXT,kind TEXT,body TEXT);
        CREATE INDEX IF NOT EXISTS timeline_viewer ON timeline(user_id,at,seq);
        ''')
    def add_event(self, event):
        added=self.db.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?)', (
            event['event_id'], event['user_id'], iso(ts(event['received_at'])), json.dumps(event))).rowcount == 1
        if added and event['event'] in ('message_delivered','message_failed','home_page_shown'):
            props=event.get('properties',{})
            aid=props.get('action_id') or props.get('page_action_id')
            if aid:
                row=self.db.execute('SELECT body FROM outbox WHERE action_id=? AND user_id=?',(aid,event['user_id'])).fetchone()
                action=json.loads(row[0]) if row else {}
                valid=(event['event']=='home_page_shown' and action.get('type')=='home_page' and props.get('personalised') is True) or (
                    event['event'] in ('message_delivered','message_failed') and action.get('type') in ('push','whatsapp') and props.get('channel')==action.get('type')
                    and (not props.get('title_id') or props['title_id']==action.get('title_id')))
                if valid:
                    status={'message_delivered':'delivered','message_failed':'failed','home_page_shown':'shown'}[event['event']]
                    self.db.execute("UPDATE outbox SET status=? WHERE action_id=? AND user_id=? AND status NOT IN ('delivered','shown')",(status,aid,event['user_id']))
                    self.record(event['user_id'],iso(ts(event['received_at'])),'delivery_observation',{'action_id':aid,'event_id':event['event_id'],'status':status})
        return added
    def history(self, user_id, at):
        return [json.loads(r[0]) for r in self.db.execute(
            'SELECT body FROM events WHERE user_id=? AND received_at<=? ORDER BY received_at,id', (user_id, at))]
    def put_goal(self, goal):
        existing=self.db.execute('SELECT body FROM goals WHERE id=?',(goal['id'],)).fetchone()
        if existing and json.loads(existing[0])==goal:
            return
        self.db.execute('INSERT INTO goals VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,body=excluded.body',
            (goal['id'], goal['user_id'], goal['goal_id'], goal['status'], json.dumps(goal)))
        self.record(goal['user_id'],goal.get('judged_at') or goal.get('revised_at') or goal.get('started_at'),'goal',goal)
    def goals(self, user_id=None, open_only=False, rule=None):
        query, args, clauses = 'SELECT body FROM goals', [], []
        for key, value in (('user_id', user_id), ('goal_id', rule), ('status', 'open' if open_only else None)):
            if value is not None:
                clauses.append(key + '=?')
                args.append(value)
        return [json.loads(r[0]) for r in self.db.execute(query + (' WHERE ' + ' AND '.join(clauses) if clauses else ''), args)]
    def decision(self, event_id):
        row = self.db.execute('SELECT body FROM decisions WHERE trigger_id=?', (event_id,)).fetchone()
        return json.loads(row[0]) if row else None
    def save_decision(self, decision, state, action=None):
        self.db.execute('INSERT INTO decisions VALUES(?,?,?,?)', (decision['decision_id'], decision['trigger_event_id'], decision['user_id'], json.dumps(decision)))
        if action:
            self.db.execute("UPDATE outbox SET status='cancelled' WHERE user_id=? AND status='pending'",(action['user_id'],))
            self.db.execute('INSERT INTO actions VALUES(?,?,?)', (action['action_id'], decision['decision_id'], json.dumps(action)))
            self.db.execute('INSERT OR REPLACE INTO plans VALUES(?,?,?,?,?)',(action['user_id'],action.get('goal_instance_id'),action['action_id'],'active',json.dumps(action)))
            self.db.execute('INSERT INTO outbox VALUES(?,?,?,?)',(action['action_id'],action['user_id'],'pending',json.dumps(action)))
        self.record(decision['user_id'],decision.get('published_at'),'decision',decision)
        self.save_state(decision['user_id'], state)
    def state(self, user_id):
        row=self.db.execute('SELECT body FROM viewer_state WHERE user_id=?',(user_id,)).fetchone()
        return json.loads(row[0]) if row else None
    def latest_action(self, user_id):
        row=self.db.execute('SELECT a.body FROM actions a JOIN decisions d ON a.decision_id=d.id WHERE d.user_id=? ORDER BY a.rowid DESC LIMIT 1',(user_id,)).fetchone()
        return json.loads(row[0]) if row else None
    def actions(self,user_id):
        return [json.loads(r[0]) for r in self.db.execute('SELECT a.body FROM actions a JOIN decisions d ON a.decision_id=d.id WHERE d.user_id=?',(user_id,))]
    def cancel_plan(self,user_id,at,reason):
        self.db.execute("UPDATE plans SET status='cancelled' WHERE user_id=?",(user_id,))
        self.db.execute("UPDATE outbox SET status='cancelled' WHERE user_id=? AND status='pending'",(user_id,))
        self.record(user_id,at,'plan_cancelled',{'reason':reason})
    def record(self,user_id,at,kind,body):
        if at:
            self.db.execute('INSERT INTO timeline(user_id,at,kind,body) VALUES(?,?,?,?)',(user_id,at,kind,json.dumps(body)))
    def timeline(self,user_id,at=None):
        return [{'at':r[0],'kind':r[1],'body':json.loads(r[2])} for r in self.db.execute(
            'SELECT at,kind,body FROM timeline WHERE user_id=? AND (? IS NULL OR at<=?) ORDER BY at,seq',(user_id,at,at))]
    def save_state(self, user_id, state):
        self.db.execute('INSERT OR REPLACE INTO viewer_state VALUES(?,?)', (user_id, json.dumps(state)))
    def export_rows(self, table):
        if table not in {'decisions', 'actions', 'goals', 'viewer_state', 'controls'}:
            raise ValueError('Unknown export table')
        return [json.loads(r[0]) for r in self.db.execute('SELECT body FROM ' + table + ' ORDER BY rowid')]
