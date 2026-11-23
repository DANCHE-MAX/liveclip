"""Validate and package a completed daily batch without fabricating clips."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile


def select_daily(report_paths):
 choices=[];seen=set()
 for report_path in map(Path,report_paths):
  report=json.loads(report_path.read_text(encoding='utf8'))
  if report.get('status')!='complete':continue
  for index,clip in enumerate(report.get('accepted',[]),1):
   p=report_path.parent/'clips'/f'clip_{index:02d}.mp4'
   if not p.is_file():raise ValueError('Accepted clip missing')
   digest=hashlib.sha256(p.read_bytes()).hexdigest()
   if digest in seen:continue
   seen.add(digest)
   duration=clip['end']-clip['start']
   if not 0<duration<=30:continue
   choices.append((0 if 15<=duration<=20 else 1,abs(duration-17.5),str(p),p))
 choices.sort(key=lambda x:x[:3])
 return [row[3] for row in choices[:50]]


def media_probe(path):
 from scripts.media_pipeline import probe
 data=probe(path)
 types={s.get('type') for s in data.get('streams',[])}
 return {'duration':data.get('duration'),'video':'video' in types,'audio':'audio' in types}


def build_bundle(clips, destination, probe=media_probe):
 if len(clips)!=50:raise ValueError('Exactly 50 clips required')
 items=[];seen=set()
 for p in map(Path,clips):
  p=p.resolve(strict=True)
  if not p.is_file() or not p.stat().st_size:raise ValueError('Empty clip')
  sha=hashlib.sha256(p.read_bytes()).hexdigest()
  if sha in seen:raise ValueError('Duplicate clip')
  seen.add(sha);info=probe(p);duration=info.get('duration')
  if not info.get('video') or not info.get('audio') or not isinstance(duration,(int,float)) or not 0<duration<=30:raise ValueError('Clip media or duration invalid')
  items.append({'name':f'{len(items)+1:02d}_{p.name}','source':str(p),'sha256':sha,'duration_seconds':duration})
 destination=Path(destination)
 if destination.exists():raise FileExistsError('Bundle already exists; preserve prior result')
 destination.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(prefix='.daily-',suffix='.zip',dir=destination.parent);os.close(fd)
 try:
  with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
   for item in items:z.write(item['source'],item['name'])
   z.writestr('manifest.json',json.dumps({'count':len(items),'clips':items},ensure_ascii=False,indent=2))
  with zipfile.ZipFile(tmp) as z:
   if z.testzip() is not None:raise ValueError('Bundle verification failed')
  os.link(tmp,destination)
 finally:
  os.unlink(tmp)
 return {'count':len(items),'path':str(destination.resolve()),'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}
