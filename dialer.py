"""Durable progressive dialer with independently bounded predictive proposals."""
import sqlite3, math, random
from contextlib import contextmanager
TERMINAL=('COMPLETED','FAILED','CANCELLED')
class Pacing:
    @staticmethod
    def propose(free, rate, mode, soon=0):
        return free if mode=='progressive' else math.ceil((free+soon)/max(.05,min(1,rate)))
class SafetyController:
    @staticmethod
    def approve(proposed, free, queued, healthy):
        return min(max(0,proposed),free,queued) if healthy else 0
class MockProvider:
    def __init__(self,name,latency,failure,noisy=False):
        self.name,self.latency,self.failure,self.noisy=name,latency,failure,noisy
        self.outage=False
    def plan(self,rng,rate,talk):
        if self.outage or rng.random()<self.failure: return [(self.latency,'FAILED')]
        if rng.random()>=rate: return [(1,'RINGING'),(self.latency,'FAILED')]
        events=[(1,'RINGING'),(self.latency,'ANSWERED'),(self.latency+talk,'COMPLETED')]
        if self.noisy: events += [(self.latency+1,'ANSWERED'),(self.latency+talk+1,'RINGING')]
        return sorted(events)
class Dialer:
    def __init__(self,path): self.path=path
    @contextmanager
    def tx(self):
        db=sqlite3.connect(self.path,timeout=30); db.row_factory=sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE'); yield db; db.commit()
        except BaseException: db.rollback(); raise
        finally: db.close()
    def setup(self,agents,borrowers):
        with self.tx() as d:
            d.execute('CREATE TABLE IF NOT EXISTS agents(id INTEGER PRIMARY KEY,state TEXT NOT NULL)')
            d.execute('CREATE TABLE IF NOT EXISTS borrowers(id INTEGER PRIMARY KEY,state TEXT NOT NULL)')
            d.execute('CREATE TABLE IF NOT EXISTS calls(id INTEGER PRIMARY KEY,agent INTEGER,borrower INTEGER,state TEXT,answered INTEGER DEFAULT 0)')
            d.execute("CREATE UNIQUE INDEX IF NOT EXISTS active_agent ON calls(agent) WHERE state NOT IN ('COMPLETED','FAILED','CANCELLED')")
            d.execute("CREATE UNIQUE INDEX IF NOT EXISTS active_borrower ON calls(borrower) WHERE state NOT IN ('COMPLETED','FAILED','CANCELLED')")
            d.execute('CREATE TABLE IF NOT EXISTS provider_jobs(call_id INTEGER PRIMARY KEY)')
            d.execute('CREATE TABLE IF NOT EXISTS events(call_id INTEGER, due INTEGER, state TEXT, PRIMARY KEY(call_id,due,state))')
            d.execute('CREATE TABLE IF NOT EXISTS health(id INTEGER PRIMARY KEY, failures INTEGER, blocked_until INTEGER)')
            d.execute('INSERT OR IGNORE INTO health VALUES(1,0,0)')
            d.executemany("INSERT OR IGNORE INTO agents VALUES(?,'AVAILABLE')",((i,) for i in range(agents)))
            d.executemany("INSERT OR IGNORE INTO borrowers VALUES(?,'QUEUED')",((i,) for i in range(borrowers)))
    def allocate(self,rate=.5,mode='progressive',now=0,outage=False):
        with self.tx() as d:
            a=d.execute("SELECT id FROM agents WHERE state='AVAILABLE' ORDER BY id").fetchall(); b=d.execute("SELECT id FROM borrowers WHERE state='QUEUED' ORDER BY id LIMIT ?",(len(a),)).fetchall()
            h=d.execute('SELECT * FROM health').fetchone(); proposed=Pacing.propose(len(a),rate,mode); n=SafetyController.approve(proposed,len(a),len(b),not outage and now>=h['blocked_until'])
            ids=[]
            for x,y in zip(a[:n],b[:n]):
                d.execute("UPDATE agents SET state='RESERVED' WHERE id=?",(x[0],)); d.execute("UPDATE borrowers SET state='RESERVED' WHERE id=?",(y[0],)); ids.append(d.execute("INSERT INTO calls(agent,borrower,state) VALUES(?,?,'RESERVED')",(x[0],y[0])).lastrowid)
            return ids,proposed,n
    def start(self,cid,provider,rng,rate,talk,now):
        with self.tx() as d:
            c=d.execute('SELECT * FROM calls WHERE id=?',(cid,)).fetchone()
            if c['state']!='RESERVED': return False
            h=d.execute('SELECT * FROM health').fetchone()
            if provider.outage or now<h['blocked_until']:
                self._event(d,cid,'CANCELLED',now); return False
            d.execute('INSERT INTO provider_jobs VALUES(?)',(cid,)); d.execute("UPDATE calls SET state='INITIATED' WHERE id=?",(cid,)); d.execute("UPDATE agents SET state='DIALING' WHERE id=?",(c['agent'],))
            d.executemany('INSERT OR IGNORE INTO events VALUES(?,?,?)',((cid,now+delay,e) for delay,e in provider.plan(rng,rate,talk)))
            return True
    def _event(self,d,cid,e,now):
        c=d.execute('SELECT * FROM calls WHERE id=?',(cid,)).fetchone()
        if not c or c['state'] in TERMINAL: return
        a=c['agent']; state=c['state']
        if e=='ANSWERED' and state in ('INITIATED','RINGING'):
            d.execute("UPDATE calls SET state='CONNECTED',answered=1 WHERE id=?",(cid,)); d.execute("UPDATE agents SET state='CONNECTED' WHERE id=?",(a,))
        elif e=='RINGING' and state=='INITIATED': d.execute("UPDATE calls SET state='RINGING' WHERE id=?",(cid,))
        elif e in TERMINAL:
            d.execute('UPDATE calls SET state=? WHERE id=?',(e,cid)); d.execute("UPDATE borrowers SET state=? WHERE id=?",('QUEUED' if e=='CANCELLED' and state=='RESERVED' else 'DONE',c['borrower'])); d.execute("UPDATE agents SET state=? WHERE id=? AND state!='OFFLINE'",('WRAP_UP' if c['answered'] else 'AVAILABLE',a))
            if e=='FAILED' and state=='INITIATED': d.execute('UPDATE health SET failures=failures+1,blocked_until=CASE WHEN failures+1>=3 THEN ? ELSE blocked_until END',(now+30,))
            elif e=='COMPLETED': d.execute('UPDATE health SET failures=0')
    def event(self,cid,e,now=0):
        with self.tx() as d: self._event(d,cid,e,now)
    def tick(self,now):
        with self.tx() as d:
            d.execute("UPDATE agents SET state='AVAILABLE' WHERE state='WRAP_UP'")
            for e in d.execute('SELECT * FROM events WHERE due<=? ORDER BY due,call_id',(now,)).fetchall():
                self._event(d,e['call_id'],e['state'],now); d.execute('DELETE FROM events WHERE call_id=? AND due=? AND state=?',tuple(e))
    def offline(self,a,now=0):
        with self.tx() as d:
            d.execute("UPDATE agents SET state='OFFLINE' WHERE id=?",(a,))
            for c in d.execute("SELECT id FROM calls WHERE agent=? AND state NOT IN ('COMPLETED','FAILED','CANCELLED')",(a,)).fetchall(): self._event(d,c[0],'CANCELLED',now)
    def recover(self,now):
        with self.tx() as d:
            for c in d.execute("SELECT id FROM calls WHERE state='RESERVED'").fetchall(): self._event(d,c[0],'CANCELLED',now)
        self.tick(now)
    def stats(self):
        with self.tx() as d:
            return dict(d.execute("SELECT (SELECT count(*) FROM provider_jobs) initiated,(SELECT coalesce(sum(answered),0) FROM calls) connected,(SELECT count(*) FROM agents WHERE state='CONNECTED') busy,(SELECT count(*) FROM agents WHERE state!='OFFLINE') online").fetchone())
