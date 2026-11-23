"""Package verified original windows without re-downloading or deleting them."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import zipfile


def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()


def bundle_windows(registry_path, keys, destination):
 if not keys:raise ValueError('No verified windows')
 db_path=Path(registry_path).resolve(strict=True);items={}
 with sqlite3.connect(f'file:{db_path}?mode=ro',uri=True) as db:
  for stream,peak in keys:
   row=db.execute('select status,path,sha256 from windows where stream=? and peak=?',(stream,peak)).fetchone()
   if not row or row[0]!='complete' or not row[1] or not row[2]:raise ValueError('Window not confirmed')
   p=Path(row[1]).resolve(strict=True)
   if not p.is_file() or digest(p)!=row[2]:raise ValueError('Window changed')
   if row[2] not in items:items[row[2]]={'path':p,'peaks':[]}
   items[row[2]]['peaks'].append({'stream':stream,'peak':peak})
 destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
 if destination.exists():raise FileExistsError('Existing archive requires reconciliation')
 fd,tmp=tempfile.mkstemp(prefix='.hourly-',suffix='.zip',dir=destination.parent);os.close(fd)
 try:
  manifest=[]
  with zipfile.ZipFile(tmp,'w',zipfile.ZIP_STORED,allowZip64=True) as z:
   for i,(sha,item) in enumerate(items.items(),1):
    name=f'{i:02d}_{item["path"].name}'
    z.write(item['path'],name)
    manifest.append({'name':name,'sha256':sha,'peaks':item['peaks']})
   z.writestr('manifest.json',json.dumps({'windows':manifest},ensure_ascii=False,indent=2))
  with zipfile.ZipFile(tmp) as z:
   if z.testzip() is not None:raise ValueError('Archive damaged')
   for item in manifest:
    h=hashlib.sha256()
    with z.open(item['name']) as f:
     for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    if h.hexdigest()!=item['sha256']:raise ValueError('Archived content mismatch')
  os.link(tmp,destination)
 finally:os.unlink(tmp)
 return {'count':len(items),'path':str(destination.resolve()),'sha256':digest(destination)}
