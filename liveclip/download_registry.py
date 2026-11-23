"""Durable, fail-closed deduplication of livestream downloads."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
import shutil

DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / 'data' / 'downloaded_windows.sqlite3'

class DownloadBlocked(RuntimeError):
    """Existing or uncertain download must be checked before any new attempt."""

def _key(stream, peak):
    if not isinstance(stream,str) or not stream.strip():
        raise ValueError('A stream ID is required')
    dt=datetime.fromisoformat(peak)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError('Peak time requires a timezone')
    return stream, dt.astimezone(timezone.utc).isoformat()

def _hash(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

class DownloadRegistry:
    def __init__(self,path=DEFAULT_REGISTRY,originals_dir=None):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.originals_dir=Path(originals_dir) if originals_dir else (self.path.parent/'保留原片' if self.path.resolve()==DEFAULT_REGISTRY.resolve() else None)
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS windows (stream TEXT NOT NULL, peak TEXT NOT NULL, status TEXT NOT NULL, path TEXT, sha256 TEXT, PRIMARY KEY(stream,peak))')
            db.execute('CREATE TABLE IF NOT EXISTS daily_reservations (day TEXT NOT NULL,stream TEXT NOT NULL,peak TEXT NOT NULL,PRIMARY KEY(day,stream,peak))')

    def register_existing(self,stream,peak,path):
        stream,peak=_key(stream,peak); path=Path(path).resolve(strict=True); digest=_hash(path)
        with sqlite3.connect(self.path) as db:
            old=db.execute('SELECT status,path,sha256 FROM windows WHERE stream=? AND peak=?',(stream,peak)).fetchone()
            if old:
                if old[0]=='complete' and old[2]==digest: return
                raise DownloadBlocked('Existing record conflicts or requires reconciliation')
            db.execute('INSERT INTO windows VALUES (?,?,?,?,?)',(stream,peak,'complete',str(path),digest))

    def reserve(self,stream,peak):
        stream,peak=_key(stream,peak)
        with sqlite3.connect(self.path,timeout=30) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status,path,sha256 FROM windows WHERE stream=? AND peak=?',(stream,peak)).fetchone()
            if row is None:
                db.execute('INSERT INTO windows VALUES (?,?,?,?,?)',(stream,peak,'pending',None,None))
                return {'status':'reserved'}
            if row[0]!='complete': raise DownloadBlocked('Download is pending or its outcome is unknown')
            path=Path(row[1])
            if not path.is_file() or _hash(path)!=row[2]: raise DownloadBlocked('Recorded file is missing or changed; do not download again')
            return {'status':'reuse','path':str(path)}

    def reserve_daily(self,stream,peak,day):
        from datetime import date
        date.fromisoformat(day)
        stream,peak=_key(stream,peak)
        with sqlite3.connect(self.path,timeout=30) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status,path,sha256 FROM windows WHERE stream=? AND peak=?',(stream,peak)).fetchone()
            if row:
                if row[0]!='complete':raise DownloadBlocked('Download is pending or its outcome is unknown')
                path=Path(row[1])
                if not path.is_file() or _hash(path)!=row[2]:raise DownloadBlocked('Recorded file is missing or changed')
                return {'status':'reuse','path':str(path)}
            if db.execute('SELECT count(*) FROM daily_reservations WHERE day=?',(day,)).fetchone()[0]>=11:
                raise DownloadBlocked('Daily 66-minute download budget reached')
            db.execute('INSERT INTO windows VALUES (?,?,?,?,?)',(stream,peak,'pending',None,None))
            db.execute('INSERT INTO daily_reservations VALUES (?,?,?)',(day,stream,peak))
            db.commit()
            return {'status':'reserved'}

    def finish(self,stream,peak,path):
        stream,peak=_key(stream,peak); path=Path(path).resolve(strict=True); digest=_hash(path)
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT status FROM windows WHERE stream=? AND peak=?",(stream,peak)).fetchone()!=('pending',):
                raise DownloadBlocked('No pending reservation to finish')
            if self.originals_dir is not None:
                self.originals_dir.mkdir(parents=True,exist_ok=True)
                target=(self.originals_dir/path.name).resolve()
                if target!=path:
                    if target.exists():raise DownloadBlocked('Archive destination exists; reconcile before moving')
                    shutil.move(str(path),str(target));path=target
                    if _hash(path)!=digest:raise DownloadBlocked('Archived file hash mismatch')
            result=db.execute("UPDATE windows SET status='complete',path=?,sha256=? WHERE stream=? AND peak=? AND status='pending'",(str(path),digest,stream,peak))
            if result.rowcount != 1: raise DownloadBlocked('No pending reservation to finish')
        return path

    def acquire_once(self,stream,peak,download):
        reservation=self.reserve(stream,peak)
        if reservation['status']=='reuse': return Path(reservation['path'])
        return self.finish(stream,peak,download())


def main():
    import argparse, json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=DEFAULT_REGISTRY)
    sub=parser.add_subparsers(dest='action',required=True)
    reserve=sub.add_parser('reserve'); reserve.add_argument('stream'); reserve.add_argument('peak')
    daily=sub.add_parser('reserve-daily'); daily.add_argument('stream'); daily.add_argument('peak'); daily.add_argument('day')
    finish=sub.add_parser('finish'); finish.add_argument('stream'); finish.add_argument('peak'); finish.add_argument('path',type=Path); finish.add_argument('start'); finish.add_argument('end')
    finish.add_argument('--allow-relative-timeline',action='store_true',help='Explicitly accept up to five seconds of platform export padding; do not infer absolute speech times')
    args=parser.parse_args(); registry=DownloadRegistry(args.db)
    if args.action=='reserve': result=registry.reserve(args.stream,args.peak)
    elif args.action=='reserve-daily': result=registry.reserve_daily(args.stream,args.peak,args.day)
    else:
        from .handoff import validate_download_name, validate_window
        from scripts.media_pipeline import probe
        path=args.path.resolve(strict=True)
        validate_download_name(path.name,args.start,args.end)
        media=probe(path); window=validate_window(args.peak,args.start,args.end,media['duration'],relative_window=args.allow_relative_timeline)
        if not {'audio','video'}.issubset({x['type'] for x in media['streams']}):
            raise ValueError('Downloaded media must contain video and audio')
        result={'status':'complete','path':str(registry.finish(args.stream,args.peak,path)),**window}
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__': main()
