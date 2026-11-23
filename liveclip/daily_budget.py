"""Conservative reservation of eleven new six-minute downloads per business day."""
from datetime import date
from pathlib import Path
import sqlite3

class DailyBudget:
 def __init__(self,path):
  self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
  with sqlite3.connect(self.path) as db:
   db.execute('CREATE TABLE IF NOT EXISTS reservations(day TEXT NOT NULL,window_key TEXT NOT NULL,PRIMARY KEY(day,window_key))')
 def reserve(self,day,window_key):
  date.fromisoformat(day)
  if not isinstance(window_key,str) or not window_key:raise ValueError('Window identity required')
  with sqlite3.connect(self.path) as db:
   db.execute('BEGIN IMMEDIATE')
   if db.execute('SELECT 1 FROM reservations WHERE day=? AND window_key=?',(day,window_key)).fetchone():return 'existing'
   if db.execute('SELECT count(*) FROM reservations WHERE day=?',(day,)).fetchone()[0]>=11:return 'limit_reached'
   db.execute('INSERT INTO reservations VALUES(?,?)',(day,window_key));db.commit();return 'reserved'
