"""Persistent, serial upload queue; caller supplies verified official-API adapters."""
import fcntl
import hashlib
from pathlib import Path
import sqlite3
import time

class RateLimited(Exception):
    pass

class UploadQueue:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, account TEXT NOT NULL, plan TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, status TEXT NOT NULL, UNIQUE(account,plan,sha256))')
            db.execute('CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), submitted INTEGER NOT NULL, cooldown_until REAL NOT NULL)')
            db.execute('INSERT OR IGNORE INTO meta VALUES (1,0,0)')
    def enqueue(self,account,plan,path,sha256):
        if not all(isinstance(x,str) and x for x in (account,plan,path,sha256)):raise ValueError('Missing queue identity')
        with sqlite3.connect(self.path) as db:db.execute("INSERT OR IGNORE INTO tasks(account,plan,path,sha256,status) VALUES (?,?,?,?, 'pending')",(account,plan,path,sha256))
    def enqueue_file(self,account,plan,path):
        p=Path(path).resolve(strict=True); h=hashlib.sha256()
        with p.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
        self.enqueue(account,plan,str(p),h.hexdigest())
    def stage_report(self,report_path,accounts):
        import json
        report_path=Path(report_path).resolve(strict=True)
        report=json.loads(report_path.read_text(encoding='utf8'))
        accepted=report.get('accepted')
        if report.get('status')!='complete' or not isinstance(accepted,list) or not accepted:
            raise ValueError('A completed review with accepted clips is required')
        if len(accounts)!=2 or len({a for a,_ in accounts})!=2:
            raise ValueError('Exactly two distinct destination accounts are required')
        files=[report_path.parent/'clips'/f'clip_{i:02d}.mp4' for i in range(1,len(accepted)+1)]
        for file in files:
            if not file.is_file() or file.stat().st_size==0:raise ValueError('An accepted clip is missing')
        for account,plan in accounts:
            for file in files:self.enqueue_file(account,plan,file)

    def statuses(self):
        with sqlite3.connect(self.path) as db:return [x[0] for x in db.execute('SELECT status FROM tasks ORDER BY id')]
    def reconcile(self,lookup):
        with self.path.with_suffix(self.path.suffix+'.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError('Queue is busy') from None
            with sqlite3.connect(self.path) as db:
                db.row_factory=sqlite3.Row
                db.execute("UPDATE tasks SET status='uncertain' WHERE status='inflight'");db.commit()
                rows=db.execute("SELECT * FROM tasks WHERE status='uncertain' ORDER BY id").fetchall()
                count=0
                for row in rows:
                    try: present=lookup(dict(row))
                    except Exception:present=None
                    if present is True:
                        db.execute("UPDATE tasks SET status='confirmed' WHERE id=?",(row['id'],));db.commit();count+=1
                return {'confirmed':count,'uncertain':len(rows)-count}

    def run(self,lookup,submit,verify,now=time.time,sleep=time.sleep):
        with self.path.with_suffix(self.path.suffix+'.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return 'paused_busy'
            with sqlite3.connect(self.path) as db:
                db.row_factory=sqlite3.Row
                db.execute("UPDATE tasks SET status='uncertain' WHERE status='inflight'");db.commit()
                if db.execute("SELECT 1 FROM tasks WHERE status='uncertain' LIMIT 1").fetchone():return 'paused_unverified'
                while row:=db.execute("SELECT * FROM tasks t WHERE status='pending' ORDER BY (SELECT MIN(id) FROM tasks a WHERE a.account=t.account), id LIMIT 1").fetchone():
                    item=dict(row)
                    if len(item['sha256'])==64:
                        source=Path(item['path'])
                        if not source.is_file():return 'paused_file_changed'
                        h=hashlib.sha256()
                        with source.open('rb') as f:
                            for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
                        if h.hexdigest()!=item['sha256']:return 'paused_file_changed'
                    try: prior=lookup(item)
                    except Exception: return 'paused_unverified'
                    if prior is None:return 'paused_unverified'
                    if prior is True:
                        db.execute("UPDATE tasks SET status='confirmed' WHERE id=?",(item['id'],));db.commit();continue
                    if prior is not False:return 'paused_unverified'
                    count,until=db.execute('SELECT submitted,cooldown_until FROM meta WHERE id=1').fetchone()
                    if until>now():sleep(until-now())
                    db.execute("UPDATE tasks SET status='inflight' WHERE id=?",(item['id'],));db.commit()
                    limited=False
                    try: submit(item)
                    except RateLimited: limited=True
                    except Exception:
                        db.execute("UPDATE tasks SET status='uncertain' WHERE id=?",(item['id'],));db.commit();return 'paused_unverified'
                    count+=1;until=now()+5 if count%2==0 else 0
                    db.execute('UPDATE meta SET submitted=?,cooldown_until=? WHERE id=1',(count,until))
                    db.execute("UPDATE tasks SET status='uncertain' WHERE id=?",(item['id'],));db.commit()
                    try: checked=verify(item)
                    except Exception: checked=None
                    if checked is True:
                        db.execute("UPDATE tasks SET status='confirmed' WHERE id=?",(item['id'],));db.commit()
                    if limited:return 'paused_rate_limit'
                    if checked is not True:return 'paused_unverified'
                return 'complete'
