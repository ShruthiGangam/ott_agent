"""Local durable actor workers: stable viewer partitions, no deployment required."""
import hashlib
import json
import queue
import sqlite3
import threading
import time
from datetime import datetime,timezone
from pathlib import Path
from .common import iso, ts
from .engine import Agent
from .store import Store

def partition(user_id,shards):
    return int(hashlib.sha256(user_id.encode()).hexdigest()[:16],16)%shards

class ViewerRuntime:
    """One sequential actor queue per partition; viewers never cross owners.

    Each partition has its own durable SQLite state and inbox. An OS file lock
    prevents another runtime process from taking the same partition. Partition
    count is pinned on disk; changing it requires an explicit state migration.
    """
    def __init__(self,pack,root,provider_factory,shards=4,max_model_calls=2,clock=None):
        self.pack,self.root=Path(pack),Path(root)
        self.root.mkdir(parents=True,exist_ok=True)
        routing=self.root/'routing.json'
        config={'shards':shards,'routing':'sha256-first-16-v1'}
        if routing.exists() and json.loads(routing.read_text())!=config:
            raise ValueError('partition_migration_required')
        routing.write_text(json.dumps(config))
        self.shards,self.provider_factory,self.max_model_calls=shards,provider_factory,max_model_calls
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.threads=[]
        self.stop_event=threading.Event()
        self.errors=queue.Queue()
        self.locks=[]
        self.initialized=[]
        for index in range(shards):
            handle=(self.root/f'owner-{index}.lock').open('a+b')
            try:
                if __import__('os').name=='nt':
                    import msvcrt
                    handle.seek(0)
                    if not handle.read(1):
                        handle.write(b'0'); handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:
                handle.close()
                self.close()
                raise ValueError('viewer_partition_already_owned') from None
            self.locks.append(handle)
            inbox=self.inbox(index)
            inbox.execute('CREATE TABLE IF NOT EXISTS inbox(id TEXT PRIMARY KEY,kind TEXT,received REAL,body TEXT,status TEXT)')
            inbox.commit(); inbox.close()
    def path(self,index):
        return self.root/f'partition-{index}.sqlite'
    def inbox(self,index):
        connection=sqlite3.connect(self.root/f'inbox-{index}.sqlite',timeout=5)
        connection.execute('PRAGMA journal_mode=WAL')
        return connection
    def seed(self,events):
        if self.threads:
            raise ValueError('seed_before_start')
        stores=[Store(self.path(i)) for i in range(self.shards)]
        try:
            for event in events:
                stores[partition(event['user_id'],self.shards)].add_event(event)
            for store in stores:
                store.db.commit()
        finally:
            for store in stores:
                store.db.close()
    def enqueue(self,item,kind='trigger'):
        indices=range(self.shards) if kind in ('control','timer') else [partition(item['user_id'],self.shards)]
        identity=hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest() if kind in ('control','timer') else item['event_id']
        inserted=0
        for index in indices:
            inbox=self.inbox(index)
            with inbox:
                inserted+=inbox.execute('INSERT OR IGNORE INTO inbox VALUES(?,?,?,?,?)',
                    (kind+':'+identity,kind,time.time(),json.dumps(item),'pending')).rowcount
            inbox.close()
        return inserted
    def start(self):
        for index in range(self.shards):
            ready=threading.Event(); self.initialized.append(ready)
            thread=threading.Thread(target=self._worker,args=(index,ready),daemon=True)
            self.threads.append(thread); thread.start()
        for ready in self.initialized:
            if not ready.wait(15):
                raise RuntimeError('worker_initialization_timeout')
    def _worker(self,index,ready):
        store=None
        inbox=None
        try:
            store=Store(self.path(index))
            inbox=self.inbox(index)
            agent=Agent(self.pack,store,self.provider_factory(),max_model_calls=self.max_model_calls)
            ready.set()
            next_review=0
            while not self.stop_event.is_set():
                if time.monotonic()>=next_review:
                    with store.db:
                        agent.tick(self.clock())
                    next_review=time.monotonic()+1
                row=inbox.execute("SELECT id,kind,received,body FROM inbox WHERE status='pending' ORDER BY rowid LIMIT 1").fetchone()
                if not row:
                    self.stop_event.wait(.005); continue
                identity,kind,received,body=row
                item=json.loads(body)
                queue_delay=max(0,time.time()-received)
                if kind not in ('control','timer'):
                    queue_delay=max(queue_delay,max(0,(self.clock()-ts(item.get('deliver_at') or item['received_at'])).total_seconds()))
                consumed=set()
                def arrivals_until(now):
                    for next_id,next_kind,next_body in inbox.execute("SELECT id,kind,body FROM inbox WHERE status='pending' ORDER BY rowid").fetchall():
                        if next_id==identity or next_id in consumed:
                            continue
                        pending=json.loads(next_body)
                        when=ts(pending.get('at') if next_kind in ('control','timer') else pending.get('deliver_at') or pending['received_at'])
                        if when>now:
                            continue
                        if next_kind=='control':
                            agent._apply_control(pending); consumed.add(next_id)
                        elif next_kind=='event':
                            agent.observe(pending,when); consumed.add(next_id)
                        elif next_kind=='trigger':
                            # Settings/evidence may arrive while planning; its own
                            # decision still waits for this viewer's serial owner.
                            agent.observe(pending,when)
                with store.db:
                    if kind=='control':
                        agent._apply_control(item)
                    elif kind=='timer':
                        agent.tick(ts(item['at']))
                    elif kind=='event':
                        now=ts(item['received_at'])
                        agent.observe(item,now)
                        state=store.state(item['user_id'])
                        if state and state.get('needs_replan') and item['event'] in ('purchase_completed','subscription_lapsed','notification_opt_out'):
                            trigger=dict(item,event_id='replan:'+item['event_id'],event='lifecycle_replan',deliver_at=item['received_at'])
                            agent.decide(trigger,controls_until=arrivals_until,queue_delay_s=queue_delay)
                    else:
                        store.add_event(item)
                        agent.decide(item,controls_until=arrivals_until,queue_delay_s=queue_delay)
                with inbox:
                    inbox.execute("UPDATE inbox SET status='done' WHERE id=?",(identity,))
                    for next_id in consumed:
                        inbox.execute("UPDATE inbox SET status='done' WHERE id=?",(next_id,))
        except Exception as error:
            self.errors.put({'partition':index,'error':type(error).__name__})
            ready.set()
        finally:
            if store:
                store.db.close()
            if inbox:
                inbox.close()
    def drain(self,timeout=60):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if not self.errors.empty():
                raise RuntimeError(json.dumps(self.errors.get()))
            pending=0
            for index in range(self.shards):
                inbox=self.inbox(index)
                pending+=inbox.execute("SELECT COUNT(*) FROM inbox WHERE status='pending'").fetchone()[0]
                inbox.close()
            if not pending:
                return
            time.sleep(.01)
        raise TimeoutError('runtime_drain_timeout')
    def close(self):
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=12)
        # A live worker retains ownership until it has stopped.
        if any(t.is_alive() for t in self.threads):
            raise RuntimeError('worker_still_running')
        for handle in self.locks:
            handle.close()
        self.locks=[]
