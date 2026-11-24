"""Serial, crash-safe video-library upload queue; injected API adapters."""
import fcntl
import hashlib
from pathlib import Path
import sqlite3
import time

class RateLimited(Exception):
 pass

class PlainQueue:
 def __init__(self,path):
  self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
  with sqlite3.connect(self.path) as db:
   db.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, account TEXT NOT NULL,path TEXT NOT NULL,sha256 TEXT NOT NULL,status TEXT NOT NULL,video_id TEXT,code INTEGER,UNIQUE(account,sha256))')
   db.execute('CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1),attempts INTEGER NOT NULL,cooldown_until REAL NOT NULL)')
   db.execute('INSERT OR IGNORE INTO meta VALUES(1,0,0)')
 def add(self,account,path,sha256):
  with sqlite3.connect(self.path) as d:d.execute("INSERT OR IGNORE INTO tasks(account,path,sha256,status) VALUES(?,?,?,'pending')",(str(account),str(Path(path).resolve()),sha256))
 def rows(self):
  with sqlite3.connect(self.path) as d:
   d.row_factory=sqlite3.Row;return [dict(x) for x in d.execute('SELECT * FROM tasks ORDER BY id')]
 def stage_report(self,report_path,accounts,excluded_hashes=()):
  import json
  report_path=Path(report_path).resolve(strict=True)
  report=json.loads(report_path.read_text(encoding='utf8'))
  clips=report.get('accepted')
  if report.get('status')!='complete' or not isinstance(clips,list) or not clips:raise ValueError('Completed review with accepted clips required')
  if len(accounts)!=2 or len(set(accounts))!=2:raise ValueError('Two distinct accounts required')
  files=[report_path.parent/'clips'/f'clip_{i:02d}.mp4' for i,c in enumerate(clips,1) if c.get('sha256') not in excluded_hashes]
  if any(not p.is_file() or not p.stat().st_size for p in files):raise ValueError('Rendered clip missing')
  for i,c in enumerate(clips,1):
   if c.get('sha256') in excluded_hashes:continue
   if c.get('sha256') and hashlib.sha256((report_path.parent/'clips'/f'clip_{i:02d}.mp4').read_bytes()).hexdigest()!=c['sha256']:raise ValueError('Reviewed clip hash changed')
  for account in accounts:
   for p in files:self.add(account,p,hashlib.sha256(p.read_bytes()).hexdigest())
 def import_history(self,history_path):
  history_path=Path(history_path)
  if not history_path.exists():return
  with sqlite3.connect(history_path) as old:
   old.row_factory=sqlite3.Row
   rows=old.execute("SELECT * FROM tasks WHERE status IN ('confirmed','uncertain','inflight')").fetchall()
  with sqlite3.connect(self.path) as db:
   for row in rows:
    status='confirmed' if row['status']=='confirmed' else 'uncertain'
    db.execute('INSERT OR IGNORE INTO tasks(account,path,sha256,status,video_id,code) VALUES(?,?,?,?,?,?)',(row['account'],row['path'],row['sha256'],status,row['video_id'],row['code']))
    db.execute("UPDATE tasks SET status=?,video_id=?,code=? WHERE account=? AND sha256=? AND status='pending'",(status,row['video_id'],row['code'],row['account'],row['sha256']))
 def import_verified_audit(self,audit_path,source_dir):
  import json
  audit_path=Path(audit_path)
  if not audit_path.exists():return
  for line in audit_path.read_text().splitlines():
   event=json.loads(line)
   if event.get('status') not in ('verified','already_present'):continue
   name=event.get('file','')
   if Path(name).name!=name:continue
   path=Path(source_dir)/name
   if not path.is_file():continue
   content=path.read_bytes();md5=hashlib.md5(content).hexdigest()
   matches=[m for m in event.get('matches',[]) if m.get('signature')==md5 and m.get('id')]
   if event.get('md5')!=md5 or not matches:continue
   self.add(str(event['account']),path,hashlib.sha256(content).hexdigest())
   with sqlite3.connect(self.path) as db:
    db.execute("UPDATE tasks SET status='confirmed',video_id=?,code=0 WHERE account=? AND sha256=? AND status='pending'",(str(matches[0]['id']),str(event['account']),hashlib.sha256(content).hexdigest()))
 def run(self,lookup,upload,verify,now=time.time,sleep=time.sleep,check_file=True):
  with self.path.with_suffix(self.path.suffix+'.lock').open('a') as lock:
   try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   except BlockingIOError:return 'paused_busy'
   with sqlite3.connect(self.path) as d:
    d.row_factory=sqlite3.Row
    d.execute("UPDATE tasks SET status='uncertain' WHERE status='inflight'");d.commit()
    if d.execute("SELECT 1 FROM tasks WHERE status='uncertain' LIMIT 1").fetchone():return 'paused_unverified'
    while row:=d.execute("SELECT * FROM tasks t WHERE status='pending' ORDER BY (SELECT MIN(id) FROM tasks a WHERE a.account=t.account),id LIMIT 1").fetchone():
     item=dict(row)
     if check_file:
      p=Path(item['path'])
      if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:return 'paused_file_changed'
     try:prior=lookup(item)
     except RateLimited:return 'paused_rate_limit'
     except Exception:return 'paused_unverified'
     if prior is True:
      d.execute("UPDATE tasks SET status='confirmed' WHERE id=?",(item['id'],));d.commit();continue
     if prior is not False:return 'paused_unverified'
     count,until=d.execute('SELECT attempts,cooldown_until FROM meta WHERE id=1').fetchone()
     if until>now():sleep(until-now())
     count+=1;until=now()+5 if count%2==0 else 0
     d.execute('UPDATE meta SET attempts=?,cooldown_until=? WHERE id=1',(count,until))
     d.execute("UPDATE tasks SET status='inflight' WHERE id=?",(item['id'],));d.commit()
     try:result=upload(item)
     except Exception:
      if count%2==0:d.execute('UPDATE meta SET cooldown_until=? WHERE id=1',(now()+5,))
      d.execute("UPDATE tasks SET status='uncertain' WHERE id=?",(item['id'],));d.commit()
      limited=False
      try: present=verify(item)
      except RateLimited:present=None;limited=True
      except Exception:present=None
      if present is True:d.execute("UPDATE tasks SET status='confirmed' WHERE id=?",(item['id'],));d.commit()
      return 'paused_rate_limit' if limited else 'paused_unverified'
     code=result.get('code') if isinstance(result,dict) else None
     vid=result.get('video_id') if isinstance(result,dict) else None
     if count%2==0:d.execute('UPDATE meta SET cooldown_until=? WHERE id=1',(now()+5,))
     d.execute("UPDATE tasks SET status='uncertain',video_id=?,code=? WHERE id=?",(vid,code,item['id']));d.commit()
     limited=False
     try:present=verify(item)
     except RateLimited:present=None;limited=True
     except Exception:present=None
     if present is True:d.execute("UPDATE tasks SET status='confirmed' WHERE id=?",(item['id'],));d.commit()
     if limited or code in (40100,429):return 'paused_rate_limit'
     if code!=0 or present is not True:return 'paused_unverified'
    return 'complete'
