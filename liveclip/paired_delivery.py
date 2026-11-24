"""Two distinct archives and an explicit both-readback cleanup gate."""
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile
from .doubao_audio import atomic_json
from .hourly_bundle import bundle_windows, digest
from .daily_bundle import media_probe
from .post_upload import VERSION, proof_valid

ACCOUNTS=['9000000000000003','9000000000000001']


def cleanup_ready(state):
    accounts=state.get('required_accounts',[])
    clips=state.get('clips',[])
    if len(accounts)!=2 or len(set(accounts))!=2 or not clips: return False
    if any(not c.get('sha256') or not set(accounts).issubset(c.get('confirmed_accounts',[])) for c in clips): return False
    requirement=state.get('post_upload_requirements')
    if requirement:
        if requirement!=VERSION: return False
        for clip in clips:
            videos={r.get('account'):r.get('video_id') for r in clip.get('upload_receipts',[]) if r.get('status')=='confirmed'}
            if not proof_valid(clip.get('post_upload',{}),accounts,clip['sha256'],videos): return False
    archives=state.get('archives',{})
    for kind in ('originals','highlights'):
        a=archives.get(kind,{})
        if a.get('status')!='sent' or not a.get('sha256'): return False
        proof=a.get('readback',{})
        if not proof.get('evidence_path') or any(proof.get(k) is not True for k in
            ('recipient_verified','filename_verified','upload_complete','no_failure_marker')): return False
    return True


def build_pair(reports, keys, registry_path, queue_path, destination, post_upload_path=None):
    post_upload_path=Path(post_upload_path or Path(__file__).resolve().parents[1]/'data/post_upload/state.json')
    if not post_upload_path.is_file(): raise ValueError('Verified post-upload ledger required before packaging')
    ledger=json.loads(post_upload_path.read_text())
    if ledger.get('version')!=VERSION: raise ValueError('Unknown post-upload ledger')
    keys=[(str(s),str(p)) for s,p in keys]
    registered=set()
    clips={}
    with sqlite3.connect('file:'+str(Path(queue_path).resolve(strict=True))+'?mode=ro',uri=True) as db:
        for report_path in map(Path,reports):
            report=json.loads(report_path.read_text())
            if report.get('status')!='complete': raise ValueError('Review not complete')
            mapping=report.get('source_registration',[])
            matched={(str(x['stream']),str(x['peak'])) for x in mapping}
            if not matched or not matched.issubset(set(keys)): raise ValueError('Source registration does not match requested keys')
            with sqlite3.connect('file:'+str(Path(registry_path).resolve(strict=True))+'?mode=ro',uri=True) as registry:
                for stream,peak in matched:
                    row=registry.execute('select status,path,sha256 from windows where stream=? and peak=?',(stream,peak)).fetchone()
                    if not row or row[0]!='complete' or row[2]!=report.get('source_sha256') or Path(row[1]).resolve()!=Path(report['source']).resolve():
                        raise ValueError('Report/source registry mismatch')
            registered.update(matched)
            for i,c in enumerate(report.get('accepted',[]),1):
                p=(report_path.parent/'clips'/f'clip_{i:02d}.mp4').resolve(strict=True)
                sha=digest(p);info=media_probe(p)
                if c.get('sha256')!=sha: raise ValueError('Reviewed final clip hash changed')
                if not info['audio'] or not info['video'] or not 0<info['duration']<=30: raise ValueError('Invalid final clip')
                receipts=[]
                for account in ACCOUNTS:
                    row=db.execute('select status,video_id from tasks where account=? and sha256=?',(account,sha)).fetchone()
                    if not row or row[0]!='confirmed' or not row[1]: raise ValueError('Both material libraries must confirm')
                    receipts.append({'account':account,'video_id':row[1],'status':'confirmed'})
                proof=ledger.get('clips',{}).get(sha,{})
                videos={r['account']:r['video_id'] for r in receipts}
                if sha in ledger.get('excluded',[]) or not proof_valid(proof,ACCOUNTS,sha,videos):
                    raise ValueError('Tag and running-plan post-upload confirmations required')
                clips[sha]={'source':str(p),'sha256':sha,'duration_seconds':info['duration'],
                            'confirmed_accounts':ACCOUNTS,'upload_receipts':receipts,'source_report':str(report_path.resolve()),'post_upload':proof}
    if not clips: raise ValueError('No qualifying clips; never send empty archives')
    if registered!=set(keys): raise ValueError('Unmapped extra original window')
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    state={'status':'preparing','required_accounts':ACCOUNTS,'clips':list(clips.values()),
           'original_keys':[{'stream':s,'peak':p} for s,p in keys],'archives':{},
           'cleanup':{'status':'blocked_until_both_archives_sent_and_readback'},
           'format_version':'paired_zip_v1','post_upload_requirements':VERSION,
           'post_upload_evidence_path':str(post_upload_path.resolve())}
    state_path=destination/'delivery_state.json';atomic_json(state_path,state)
    original=bundle_windows(registry_path,keys,destination/'originals_6min.zip')
    state['archives']['originals']={**original,'status':'ready'};atomic_json(state_path,state)
    target=destination/'highlights.zip';temporary=destination/'.highlights.zip.tmp'
    entries=[]
    with zipfile.ZipFile(temporary,'x',zipfile.ZIP_STORED) as z:
        for i,item in enumerate(clips.values(),1):
            entry={**item,'name':f'{i:02d}_{Path(item["source"]).name}'}
            z.write(item['source'],entry['name']);entries.append(entry)
        z.writestr('manifest.json',json.dumps({'count':len(entries),'clips':entries},ensure_ascii=False,indent=2))
    with zipfile.ZipFile(temporary) as z:
        if z.testzip() is not None: raise ValueError('ZIP integrity failed')
        for entry in entries:
            if hashlib.sha256(z.read(entry['name'])).hexdigest()!=entry['sha256']: raise ValueError('ZIP hash mismatch')
    temporary.replace(target)
    state['archives']['highlights']={'path':str(target.resolve()),'count':len(entries),'sha256':digest(target),'status':'ready'}
    state['status']='ready';atomic_json(state_path,state)
    return state
