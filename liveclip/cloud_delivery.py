"""Fail-closed private cloud delivery state machine, with injectable adapters."""
import fcntl
import hashlib
from pathlib import Path
import sqlite3


def private_for_external_download(settings):
 return (isinstance(settings,dict) and settings.get('link_share_entity')=='closed'
         and settings.get('external_access') is True
         and settings.get('security_entity')=='anyone_can_view'
         and settings.get('share_entity')=='only_full_access')


def deliver_cloud(db_path,day,bundle,recipient,upload,private_check,grant,send):
 bundle=Path(bundle).resolve(strict=True)
 sha=hashlib.sha256(bundle.read_bytes()).hexdigest()
 db_path=Path(db_path);db_path.parent.mkdir(parents=True,exist_ok=True)
 with db_path.with_suffix(db_path.suffix+'.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return 'busy'
  with sqlite3.connect(db_path) as db:
   db.execute('CREATE TABLE IF NOT EXISTS deliveries(day TEXT PRIMARY KEY,sha TEXT NOT NULL,recipient TEXT NOT NULL,status TEXT NOT NULL,token TEXT,url TEXT,message_id TEXT)')
   row=db.execute('SELECT sha,recipient,status,token,url FROM deliveries WHERE day=?',(day,)).fetchone()
   if row:
    if row[0]!=sha or row[1]!=recipient:raise ValueError('Batch identity differs from recorded delivery')
    if row[2]=='sent':return 'sent'
    return 'blocked' if row[2]=='blocked' else 'uncertain'
   db.execute("INSERT INTO deliveries(day,sha,recipient,status) VALUES(?,?,?,'uploading')",(day,sha,recipient));db.commit()
   try:
    result=upload(bundle);token=result['token'];url=result['url']
    if not token or not url:raise ValueError('Missing cloud file identity')
   except Exception:
    db.execute("UPDATE deliveries SET status='uncertain' WHERE day=?",(day,));db.commit();return 'uncertain'
   db.execute("UPDATE deliveries SET status='checking',token=?,url=? WHERE day=?",(token,url,day));db.commit()
   try:
    if private_check(token) is not True:
     db.execute("UPDATE deliveries SET status='blocked' WHERE day=?",(day,));db.commit();return 'blocked'
    db.execute("UPDATE deliveries SET status='granting' WHERE day=?",(day,));db.commit()
    if grant(token,recipient) is not True:raise ValueError('Grant unverified')
    db.execute("UPDATE deliveries SET status='sending' WHERE day=?",(day,));db.commit()
    key=hashlib.sha256((day+sha+recipient).encode()).hexdigest()[:40]
    message_id=send(url,recipient,key)
    if not message_id:raise ValueError('Missing message ID')
   except Exception:
    db.execute("UPDATE deliveries SET status='uncertain' WHERE day=?",(day,));db.commit();return 'uncertain'
   db.execute("UPDATE deliveries SET status='sent',message_id=? WHERE day=?",(str(message_id),day));db.commit();return 'sent'
