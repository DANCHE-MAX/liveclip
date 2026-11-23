#!/usr/bin/env python3
"""Upload the four user-approved clips to two material libraries, without tags."""
import hashlib, importlib.util, json, os, pathlib, sqlite3, sys, time, urllib.error, urllib.parse, urllib.request, uuid
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from liveclip.plain_upload import PlainQueue, RateLimited
from liveclip.qianchuan_auth import load_service, verified_token
ROOT=pathlib.Path(__file__).resolve().parents[1]
ACCOUNTS=('9000000000000003','9000000000000001')
OUT=ROOT/'data/library_upload'
OUT.mkdir(parents=True,exist_ok=True)
q=PlainQueue(OUT/'queue.sqlite3')

def log(event, **fields):
 record={'time':time.strftime('%Y-%m-%d %H:%M:%S %z'),'event':event,**fields}
 with (OUT/'audit.jsonl').open('a') as f:
  f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
 print(json.dumps(record,ensure_ascii=False),flush=True)

def http_json(req,timeout=25):
 try:
  with urllib.request.urlopen(req,timeout=timeout) as response:return json.load(response)
 except urllib.error.HTTPError as e:
  if e.code==429:raise RateLimited()
  raise RuntimeError('http_'+str(e.code)) from None

def main():
 module=load_service()
 # Port 8080 now belongs to the separate workbench-label OAuth app. Probe the
 # actual Qianchuan credential and each destination before any upload instead.
 token=verified_token(module,ACCOUNTS)
 if len(sys.argv)!=2:raise RuntimeError('review_report_required')
 q.stage_report(sys.argv[1],ACCOUNTS)
 expected={}
 def signature(row):return hashlib.md5(pathlib.Path(row['path']).read_bytes()).hexdigest()
 def find(row):
  sig=signature(row);query=urllib.parse.urlencode({'advertiser_id':row['account'],'filtering':json.dumps({'signatures':[sig]},separators=(',',':')),'page':1,'page_size':100})
  res=http_json(urllib.request.Request('https://api.oceanengine.com/open_api/v1.0/qianchuan/video/get/?'+query,headers={'Access-Token':token}))
  code=res.get('code')
  if code in (40100,429):raise RateLimited()
  if code!=0:raise RuntimeError('readback_code_'+str(code))
  data=res.get('data') or {};items=data.get('list')
  if not isinstance(items,list) or (data.get('page_info') or {}).get('total_page',1)>1:raise RuntimeError('invalid_readback')
  return [x for x in items if x.get('signature')==sig]
 def lookup(row):
  found=find(row)
  if found:log('existing',account=row['account'],file=pathlib.Path(row['path']).name,video_ids=[str(x.get('id')) for x in found])
  return bool(found)
 def upload(row):
  path=pathlib.Path(row['path']);sig=signature(row);boundary='----Liveclip'+uuid.uuid4().hex
  fields={'advertiser_id':row['account'],'upload_type':'UPLOAD_BY_FILE','video_signature':sig,'filename':'直播切片_'+path.name};body=bytearray()
  for k,v in fields.items():body.extend(('--'+boundary+'\r\nContent-Disposition: form-data; name="'+k+'"\r\n\r\n'+v+'\r\n').encode())
  body.extend(('--'+boundary+'\r\nContent-Disposition: form-data; name="video_file"; filename="'+path.name+'"\r\nContent-Type: video/mp4\r\n\r\n').encode());body.extend(path.read_bytes());body.extend(('\r\n--'+boundary+'--\r\n').encode())
  log('upload_started',account=row['account'],file=path.name)
  req=urllib.request.Request('https://ad.oceanengine.com/open_api/2/file/video/ad/',data=bytes(body),headers={'Access-Token':token,'Content-Type':'multipart/form-data; boundary='+boundary},method='POST')
  try:res=http_json(req,timeout=90)
  except RateLimited:
   log('upload_rate_limited',account=row['account'],file=path.name)
   return {'code':429}
  data=res.get('data') or {};vid=data.get('video_id');code=res.get('code')
  if vid:expected[row['id']]=str(vid)
  log('upload_response',account=row['account'],file=path.name,code=code,video_id=vid,material_id=data.get('material_id'),request_id=res.get('request_id'))
  return {'code':code,'video_id':str(vid) if vid else None}
 def verify(row):
  target=expected.get(row['id'])
  if not target:return None
  for i in range(7):
   found=find(row)
   if any(str(x.get('id'))==target for x in found):
    log('verified',account=row['account'],file=pathlib.Path(row['path']).name,video_id=target)
    return True
   if i<6:time.sleep(5)
  log('readback_pending',account=row['account'],file=pathlib.Path(row['path']).name,video_id=target)
  return None
 result=q.run(lookup,upload,verify)
 log('queue_stopped',result=result,rows=[{'account':r['account'],'file':pathlib.Path(r['path']).name,'status':r['status'],'video_id':r['video_id'],'code':r['code']} for r in q.rows()])
 return 0 if result=='complete' else 2
if __name__=='__main__':
 try:sys.exit(main())
 except Exception as e:
  log('fatal',error_type=type(e).__name__,detail=str(e) if isinstance(e,RuntimeError) else 'see local checks')
  sys.exit(2)
