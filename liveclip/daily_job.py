"""Prepare a single day's explicitly supplied reviewed clips for delivery."""
import argparse
import json
import hashlib
import sqlite3
from pathlib import Path
from .daily_bundle import select_daily,build_bundle


ACCOUNTS=('9000000000000003','9000000000000001')
DEFAULT_UPLOAD_DB=Path(__file__).resolve().parents[1]/'data/library_upload/queue.sqlite3'

def all_uploaded(clips,db_path,accounts=ACCOUNTS):
 if len(accounts)!=2 or len(set(accounts))!=2 or not Path(db_path).is_file():return False
 try:
  with sqlite3.connect(f'file:{Path(db_path).resolve()}?mode=ro',uri=True) as db:
   for path in clips:
    digest=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    for account in accounts:
     row=db.execute('SELECT status FROM tasks WHERE account=? AND sha256=?',(account,digest)).fetchone()
     if not row or row[0]!='confirmed':return False
 except (OSError,sqlite3.Error):return False
 return True

def prepare_daily(reports, destination, upload_db=DEFAULT_UPLOAD_DB):
 clips=select_daily(reports)
 if len(clips)<50:return {'status':'insufficient_clips','count':len(clips),'target':50}
 if not all_uploaded(clips,upload_db):return {'status':'uploads_unconfirmed','count':len(clips),'target':50}
 return {'status':'ready',**build_bundle(clips,destination)}


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('reports',nargs='+',type=Path)
 parser.add_argument('--output',required=True,type=Path)
 args=parser.parse_args()
 result=prepare_daily(args.reports,args.output)
 print(json.dumps(result,ensure_ascii=False,indent=2))
 if result['status']!='ready':raise SystemExit(2)

if __name__=='__main__':main()
