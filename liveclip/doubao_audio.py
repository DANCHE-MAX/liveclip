"""Durable, single-submission Ark Responses audio/image review."""
import base64
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
from .model import decode_json

ENDPOINT = 'https://ark.cn-beijing.volces.com/api/v3/responses'


def atomic_json(path, data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    with temporary.open('w',encoding='utf8') as f:
        json.dump(data,f,ensure_ascii=False,indent=2);f.flush()
        import os
        os.fsync(f.fileno())
    temporary.replace(path)


def review_cached(client, prompt, audio, cache, images=(), max_output_tokens=14000, schema=None):
    if client.provider!='doubao': raise ValueError('Ark audio requires the Doubao client')
    key=client.get_key()
    if not key: raise RuntimeError('needs_configuration: local ARK_API_KEY')
    audio=Path(audio) if audio is not None else None
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    data=audio.read_bytes() if audio is not None else None
    audio_hash=hashlib.sha256(data).hexdigest() if data is not None else None
    signature={'model':client.model,'audio_sha256':audio_hash,'prompt':prompt,
               'image_sha256':[hashlib.sha256(s.encode()).hexdigest() for s in images],
               'max_output_tokens':max_output_tokens,'thinking':'disabled','schema':schema,'json_format_version':1}
    request_key=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()
    path=cache/(request_key+'.json')
    with (cache/(request_key+'.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if path.exists():
            old=json.loads(path.read_text())
            if old.get('status')=='complete': return old['decision']
            raise RuntimeError('Ark request requires reconciliation; do not resubmit: '+request_key)
        content=[]
        if audio is not None:
            mime={'wav':'audio/wav','mp3':'audio/mpeg','m4a':'audio/x-m4a'}.get(audio.suffix[1:].lower())
            if mime is None: raise ValueError('Unsupported audio format')
            content.append({'type':'input_audio','audio_url':'data:'+mime+';base64,'+base64.b64encode(data).decode()})
        content.extend({'type':'input_image','image_url':s} for s in images)
        content.append({'type':'input_text','text':prompt})
        body={'model':client.model,'thinking':{'type':'disabled'},'max_output_tokens':max_output_tokens,
              'input':[{'role':'user','content':content}]}
        body['text']={'format':{'type':'json_schema','name':'liveclip_result','strict':True,'schema':schema} if schema else {'type':'json_object'}}
        record={'status':'sending','request_key':request_key,'model':client.model,'audio_sha256':audio_hash,
                'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'image_sha256':signature['image_sha256'],
                'submitted_at':datetime.now(timezone.utc).isoformat()}
        atomic_json(path,record);started=time.monotonic()
        req=urllib.request.Request(ENDPOINT,data=json.dumps(body,ensure_ascii=False).encode(),
                                  headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=240) as response:
                result=json.load(response)
                record['request_id']=getattr(response,'headers',{}).get('x-request-id')
        except urllib.error.HTTPError as error:
            record.update(status='http_error',http_status=error.code,elapsed_seconds=time.monotonic()-started)
            atomic_json(path,record)
            raise RuntimeError('doubao_http_error_'+str(error.code)) from None
        except (urllib.error.URLError,TimeoutError,OSError):
            record.update(status='result_uncertain',elapsed_seconds=time.monotonic()-started)
            atomic_json(path,record)
            raise RuntimeError('doubao_result_uncertain; inspect before retry') from None
        record.update(response=result,elapsed_seconds=time.monotonic()-started)
        atomic_json(path,record)
        client.usage.append({**result.get('usage',{}),'response_id':result.get('id'),
                             'request_id':record['request_id'],'submitted_at':record['submitted_at'],
                             'elapsed_seconds':record['elapsed_seconds'],'audio_sha256':audio_hash,
                             'receipt_path':str(path.resolve())})
        if result.get('status')!='completed' or result.get('model')!=client.model:
            record['status']='incomplete_or_wrong_model';atomic_json(path,record)
            raise ValueError('Ark response incomplete or model differs')
        text='\n'.join(c.get('text','') for item in result.get('output',[])
                       for c in item.get('content',[]) if c.get('type')=='output_text').strip()
        try:
            decision=decode_json(text)
        except ValueError:
            record['status']='invalid_json';atomic_json(path,record)
            raise ValueError('Invalid Ark JSON; preserve receipt, no automatic retry') from None
        record.update(status='complete',decision=decision);atomic_json(path,record)
        return decision
