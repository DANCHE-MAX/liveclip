"""Persistent at-most-once handoff for a daily bundle."""
import hashlib
from pathlib import Path
import sqlite3
import json
import subprocess


def send_lark_file(bundle,recipient,idempotency_key,runner=subprocess.run):
 bundle=Path(bundle).resolve(strict=True)
 if bundle.stat().st_size>30_000_000:raise ValueError('Message attachment exceeds 30 MB')
 result=runner(['lark-cli','im','+messages-send','--user-id',recipient,'--file','./'+bundle.name,'--as','user','--idempotency-key',idempotency_key],cwd=str(bundle.parent),capture_output=True,text=True,timeout=180)
 if result.returncode!=0:raise RuntimeError('Feishu send failed or unconfirmed')
 response=json.loads(result.stdout)
 if response.get('ok') is not True or not (response.get('data') or {}).get('message_id'):raise ValueError('Feishu response missing message ID')
 return response['data']['message_id']


def deliver(db_path,day,bundle,recipient,send):
 bundle=Path(bundle).resolve(strict=True)
 digest=hashlib.sha256(bundle.read_bytes()).hexdigest()
 with sqlite3.connect(db_path) as db:
  db.execute('CREATE TABLE IF NOT EXISTS deliveries(day TEXT PRIMARY KEY,sha256 TEXT NOT NULL,recipient TEXT NOT NULL,status TEXT NOT NULL,message_id TEXT)')
  db.execute('BEGIN IMMEDIATE')
  old=db.execute('SELECT sha256,recipient,status FROM deliveries WHERE day=?',(day,)).fetchone()
  if old:
   if old[0]!=digest or old[1]!=recipient:raise ValueError('Existing daily delivery has different contents or recipient')
   return 'uncertain' if old[2]=='inflight' else old[2]
  db.execute("INSERT INTO deliveries VALUES(?,?,?,'inflight',NULL)",(day,digest,recipient));db.commit()
  try:
   message_id=send(bundle,recipient,hashlib.sha256((day+digest+recipient).encode()).hexdigest()[:40])
   if not message_id:raise ValueError('Missing message ID')
  except Exception:
   db.execute("UPDATE deliveries SET status='uncertain' WHERE day=?",(day,));db.commit();return 'uncertain'
  db.execute("UPDATE deliveries SET status='sent',message_id=? WHERE day=?",(str(message_id),day));db.commit();return 'sent'
