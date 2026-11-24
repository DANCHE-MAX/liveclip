"""Future-batch tag readback and additive running-live-plan enrollment.

Missing tags are a hard handoff to an authorized official tagging channel, not
an invitation to call an unrelated product API. No tag write endpoint is guessed.
"""
import fcntl
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from .doubao_audio import atomic_json

VERSION = 'tag_and_running_plans_v1'
ACCOUNTS = ['9000000000000003', '9000000000000001']

class Blocked(RuntimeError):
    pass

def now():
    return datetime.now(timezone.utc).isoformat()

def proof_valid(proof, accounts, sha, videos=None):
    if proof.get('version') != VERSION or proof.get('sha256') != sha or proof.get('status') != 'confirmed':
        return False
    if set(proof.get('accounts', {})) != set(accounts): return False
    for account in accounts:
        row = proof['accounts'][account]
        if not row.get('video_id') or videos is not None and row['video_id'] != videos.get(account): return False
        tag = row.get('tag', {})
        if tag.get('status') != 'confirmed' or tag.get('label') != '切片' or not tag.get('checked_at') or not tag.get('request_id'): return False
        plans = row.get('required_plan_ids', [])
        if not plans or len(plans) != len(set(plans)) or not row.get('plan_snapshot_at'): return False
        for plan in plans:
            p = row.get('plans', {}).get(plan, {})
            if p.get('status') != 'confirmed' or not p.get('checked_at') or not p.get('request_id'): return False
            if p.get('video_id') != row['video_id'] or p.get('running_at_write') is not True: return False
            if p.get('all_original_retained') is not True or row['video_id'] not in p.get('after_ids', []): return False
            if not set(p.get('before_ids', [])).issubset(p.get('after_ids', [])): return False
    return True

class PostUpload:
    def __init__(self, state_path, accounts=ACCOUNTS, exclusions=(), sleep=time.sleep):
        self.path = Path(state_path)
        self.accounts = list(accounts)
        if self.accounts != ACCOUNTS: raise ValueError('Only the two authorized accounts')
        self.exclusions = set(exclusions)
        self.sleep = sleep

    def tag_intent(self, account, sha, before_tags=None, evidence_path=None):
        if sha in self.exclusions or account not in self.accounts: raise Blocked('excluded or unauthorized tag target')
        with self.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state=json.loads(self.path.read_text())
            row=state.get('clips',{}).get(sha,{}).get('accounts',{}).get(account,{})
            tag=row.get('tag',{})
            if tag.get('status')=='unknown':
                evidence=Path(evidence_path) if evidence_path else None
                if not isinstance(before_tags,list) or not all(isinstance(t,str) for t in before_tags) or evidence is None or evidence.is_symlink() or not evidence.is_file():
                    raise Blocked('unknown tags require actual official UI preflight evidence')
                tag.update(before_tags=before_tags,ui_preflight_evidence=str(evidence.resolve()),
                           ui_preflight_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest())
            elif tag.get('status')!='needs_official_tagging': raise Blocked('tag intent missing, already submitted or uncertain')
            tag.update(status='sending',write_intent_at=now(),channel='official_qianchuan_ui')
            atomic_json(self.path,state)
            return row

    def process(self, clips, adapter):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state = json.loads(self.path.read_text()) if self.path.exists() else {'version': VERSION, 'clips': {}, 'excluded': []}
            if state.get('version') != VERSION: raise Blocked('ledger version mismatch')
            state['excluded'] = sorted(set(state.get('excluded', [])) | self.exclusions)
            def save():
                state['updated_at'] = now(); atomic_json(self.path, state)
            state['status'] = 'processing'; save()
            try:
                for clip in clips:
                    sha = clip['sha256']
                    if sha in self.exclusions:
                        state['excluded'] = sorted(set(state['excluded']) | {sha}); save(); continue
                    path = Path(clip['path'])
                    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                        raise Blocked('clip hash/path changed')
                    if set(clip.get('videos', {})) != set(self.accounts) or not all(clip['videos'].values()):
                        raise Blocked('both library confirmations required')
                    proof = state['clips'].setdefault(sha, {'version': VERSION, 'sha256': sha, 'accounts': {}})
                    proof['status'] = 'processing'; save()
                    for account in self.accounts:
                        video = clip['videos'][account]
                        row = proof['accounts'].setdefault(account, {'video_id': video, 'plans': {}})
                        if row['video_id'] != video: raise Blocked('video identity changed')
                        found = adapter.video(clip, account)
                        if found.get('id') != video or found.get('signature') != clip['md5']: raise Blocked('video readback unknown')
                        row['library_readback']={k:found.get(k) for k in ('id','material_id','filename','signature','request_id')}
                        if not isinstance(found.get('tags'),list):
                            if row.get('tag',{}).get('status') not in ('sending','uncertain'):
                                row['tag']={'label':'切片','status':'unknown','checked_at':now(),'request_id':found.get('request_id')}
                            save();raise Blocked('tag readback unknown; null is not empty')
                        tags = found['tags']
                        if not all(isinstance(t, str) for t in tags): raise Blocked('tag format unknown')
                        old_tag=row.get('tag',{})
                        if '切片' not in tags and old_tag.get('status') in ('sending','uncertain'):
                            old_tag.update(status='uncertain',last_readback_at=now(),last_observed_tags=tags);save()
                            raise Blocked('prior tag write uncertain; readback only, never repeat')
                        previous = row.get('tag', {}).get('before_tags', tags)
                        row['tag'] = {**old_tag,'label': '切片', 'before_tags': previous, 'observed_tags': tags,
                                      'status': 'confirmed' if '切片' in tags else 'needs_official_tagging',
                                      'checked_at': now(), 'request_id': found.get('request_id')}
                        save()
                        if '切片' not in tags: raise Blocked('tag missing; official tagging and independent readback required')
                        if not set(previous).issubset(tags): raise Blocked('previous tags not retained')
                        if not found.get('request_id'): raise Blocked('tag readback evidence missing')
                        plans = adapter.running_plans(account)
                        if not plans: raise Blocked('no verified running live plan')
                        if len({str(p['id']) for p in plans}) != len(plans): raise Blocked('duplicate plan inventory')
                        if any(p.get('status') != 'DELIVERY_OK' or p.get('opt_status') != 'ENABLE' or p.get('marketing_goal') != 'LIVE_PROM_GOODS' for p in plans):
                            raise Blocked('running plan inventory invalid')
                        row['required_plan_ids'] = [str(p['id']) for p in plans]
                        row['plan_snapshot_at'] = now(); save()
                        for plan in row['required_plan_ids']:
                            detail = adapter.detail(account, plan)
                            if not self._running(detail, plan): raise Blocked('plan no longer running')
                            ids = detail.get('ids')
                            if not isinstance(ids, list) or not all(isinstance(v, str) and v for v in ids): raise Blocked('plan membership unknown')
                            journal = row['plans'].setdefault(plan, {'status': 'new', 'before_ids': ids, 'video_id': video})
                            if journal.get('video_id') != video: raise Blocked('plan video changed')
                            if not set(journal['before_ids']).issubset(ids): raise Blocked('original plan materials not retained')
                            if video not in ids:
                                if journal['status'] != 'new': raise Blocked('prior uncertain or changed plan; readback only, never repeat')
                                cover = row.get('cover', {})
                                if not cover.get('id'):
                                    if cover: raise Blocked('cover upload uncertain; no repeat')
                                    row['cover'] = {'status': 'sending', 'intent_at': now()}; save()
                                    try:
                                        cover_id = adapter.cover(clip, account)
                                        if not cover_id: raise Blocked('cover missing')
                                        row['cover'] = {'status': 'confirmed', 'id': cover_id, 'checked_at': now()}; save()
                                    except Exception:
                                        row['cover']['status'] = 'uncertain'; save(); raise Blocked('cover upload uncertain') from None
                                    self.sleep(5)
                                current = adapter.detail(account, plan)
                                if not self._running(current, plan): raise Blocked('plan stopped before append')
                                if not set(ids).issubset(current.get('ids', [])): raise Blocked('original plan materials not retained')
                                ids = current['ids']; journal['before_ids'] = ids
                                if video not in ids:
                                    journal.update(status='uncertain', intent_at=now(), running_at_write=True); save()
                                    try:
                                        response = adapter.append(account, plan, video, row['cover']['id'])
                                        journal['response'] = {k: response.get(k) for k in ('code', 'message', 'request_id')}; save()
                                        if response.get('code') != 0: raise Blocked('append API error; reconcile only')
                                    except Exception:
                                        save(); raise Blocked('append result uncertain; reconcile only') from None
                                    self.sleep(5)
                            after = adapter.detail(account, plan)
                            retained = set(journal['before_ids']).issubset(after.get('ids', []))
                            if not retained: raise Blocked('original plan materials not retained')
                            if video not in after.get('ids', []) or not self._running(after, plan):
                                raise Blocked('append readback incomplete or plan stopped')
                            if not after.get('request_id'): raise Blocked('plan evidence missing')
                            journal.update(status='confirmed', after_ids=after['ids'], all_original_retained=True,
                                           running_at_write=True, checked_at=now(), request_id=after['request_id']); save()
                    proof['status'] = 'confirmed'; save()
                    if not proof_valid(proof, self.accounts, sha, clip['videos']): raise Blocked('post-upload proof incomplete')
                state['status'] = 'complete'; state.pop('error', None); save(); return state
            except Exception as exc:
                state['status'] = 'blocked'; state['error'] = str(exc) if isinstance(exc, Blocked) else type(exc).__name__; save()
                raise

    @staticmethod
    def _running(detail, plan):
        return (str(detail.get('ad_id')) == str(plan) and detail.get('status') == 'DELIVERY_OK'
                and detail.get('opt_status') == 'ENABLE' and detail.get('marketing_goal') == 'LIVE_PROM_GOODS')

class OfficialAdapter:
    """Official Qianchuan reads and material/add only; credentials never logged."""
    BASE = 'https://api.oceanengine.com'
    def __init__(self, token):
        self.token = token
        self.last_request = 0

    def _request(self, path, params, *, body=None):
        import urllib.parse, urllib.request
        time.sleep(max(0, 1.5 - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        headers = {'Access-Token': self.token}
        if body is None:
            args = {k: json.dumps(v, ensure_ascii=False, separators=(',', ':')) if isinstance(v, (dict, list)) else str(v) for k, v in params.items()}
            req = urllib.request.Request(self.BASE + path + '?' + urllib.parse.urlencode(args), headers=headers)
        else:
            headers['Content-Type'] = 'application/json'
            req = urllib.request.Request(self.BASE + path, data=json.dumps(body).encode(), headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=40) as response: result = json.load(response)
        except Exception as exc:
            raise Blocked('official request failed: ' + type(exc).__name__) from None
        if body is not None and isinstance(result, dict) and result.get('request_id') and 'code' in result:
            return result
        if result.get('code') != 0:
            raise Blocked('official API code ' + str(result.get('code')) + ': ' + str(result.get('message', '')))
        if not result.get('request_id') or not isinstance(result.get('data'), dict): raise Blocked('official response incomplete')
        return result

    def video(self, clip, account):
        result = self._request('/open_api/v1.0/qianchuan/video/get/', {
            'advertiser_id': account, 'filtering': {'signatures': [clip['md5']]}, 'page': 1, 'page_size': 100})
        data = result['data']; page = data.get('page_info') or {}
        rows = [r for r in data.get('list', []) if r.get('signature') == clip['md5'] and str(r.get('id')) == clip['videos'][account]]
        if len(rows) != 1 or page.get('total_page', 1) > 1: raise Blocked('exact library video readback incomplete')
        return {**{k: rows[0].get(k) for k in ('id', 'signature', 'tags', 'material_id','filename')}, 'request_id': result['request_id']}

    def running_plans(self, account):
        from zoneinfo import ZoneInfo
        day = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')
        all_rows = {}; inventory = []
        for scene in ('OVERALL_PROJECT', 'UNI_PROJECT'):
            rows = []; expected = None
            for page in range(1, 101):
                result = self._request('/open_api/v1.0/qianchuan/uni_promotion/list/', {
                    'advertiser_id': account, 'marketing_goal': 'LIVE_PROM_GOODS', 'adlab_scene': scene,
                    'start_time': day+' 00:00:00', 'end_time': day+' 23:59:59', 'filtering': {'status': 'ALL'},
                    'page': page, 'page_size': 100})
                data = result['data']; info = data.get('page_info'); items = data.get('ad_list')
                if not isinstance(info, dict) or not isinstance(items, list): raise Blocked('plan pagination missing')
                total = info.get('total_num'); pages = info.get('total_page')
                if not isinstance(total, int) or not isinstance(pages, int) or info.get('page') != page or total < 0 or pages > 100:
                    raise Blocked('plan pagination invalid')
                if expected is not None and expected != (total, pages): raise Blocked('plan inventory changed during pagination')
                expected = (total, pages)
                for item in items:
                    ad = item.get('ad_info')
                    if not isinstance(ad, dict) or not ad.get('id') or ad.get('marketing_goal') != 'LIVE_PROM_GOODS' or ad.get('adlab_scene') != scene:
                        raise Blocked('plan identity/scene unknown')
                    key = str(ad['id'])
                    if key in all_rows: raise Blocked('duplicate plan in inventory')
                    all_rows[key] = ad; rows.append(ad)
                if page >= max(pages, 1): break
            if len(rows) != expected[0]: raise Blocked('plan inventory coverage incomplete')
            inventory.extend(rows)
        return [r for r in inventory if r.get('status') == 'DELIVERY_OK' and r.get('opt_status') == 'ENABLE']

    def detail(self, account, plan):
        result = self._request('/open_api/v1.0/qianchuan/uni_promotion/ad/detail/', {'advertiser_id': account, 'ad_id': plan})
        data = result['data']; media = data.get('programmatic_creative_media_list')
        if not isinstance(media, dict) or not isinstance(media.get('video_material'), list): raise Blocked('plan media missing')
        ids = [m.get('video_id') for m in media['video_material']]
        if not all(isinstance(v, str) and v for v in ids): raise Blocked('plan video IDs missing')
        return {**{k: data.get(k) for k in ('ad_id', 'status', 'opt_status', 'marketing_goal')}, 'ids': ids, 'request_id': result['request_id']}

    def cover(self, clip, account):
        import subprocess, tempfile, uuid, urllib.request
        import imageio_ffmpeg
        with tempfile.TemporaryDirectory(prefix='liveclip-cover-') as directory:
            target = Path(directory)/'cover.jpg'
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-ss', '1', '-i', clip['path'],
                            '-frames:v', '1', '-q:v', '3', str(target)], check=True, capture_output=True)
            raw = target.read_bytes(); boundary = 'Liveclip'+uuid.uuid4().hex; body = bytearray()
            fields = {'advertiser_id': account, 'upload_type': 'UPLOAD_BY_FILE', 'image_signature': hashlib.md5(raw).hexdigest()}
            for key, value in fields.items():
                body.extend(('--'+boundary+'\r\nContent-Disposition: form-data; name="'+key+'"\r\n\r\n'+value+'\r\n').encode())
            body.extend(('--'+boundary+'\r\nContent-Disposition: form-data; name="image_file"; filename="cover.jpg"\r\nContent-Type: image/jpeg\r\n\r\n').encode())
            body.extend(raw); body.extend(('\r\n--'+boundary+'--\r\n').encode())
            req = urllib.request.Request(self.BASE+'/open_api/2/file/image/ad/', data=bytes(body), method='POST',
                    headers={'Access-Token': self.token, 'Content-Type': 'multipart/form-data; boundary='+boundary})
            with urllib.request.urlopen(req, timeout=40) as response: result = json.load(response)
            cover_id = (result.get('data') or {}).get('id')
            if result.get('code') != 0 or not cover_id: raise Blocked('cover upload failed or incomplete')
            return cover_id

    def append(self, account, plan, video, cover):
        return self._request('/open_api/v1.0/qianchuan/uni_promotion/ad/material/add/', {}, body={
            'advertiser_id': int(account), 'ad_id': int(plan), 'programmatic_creative_media_list': {
                'video_material': [{'video_id': video, 'image_mode': 'VIDEO_VERTICAL', 'video_cover_id': cover}]}})


def excluded_report_indices(report_path,queue_path,exclusions):
    """Recognize only explicitly excluded hashes, including deleted old reports."""
    import sqlite3
    report_path=Path(report_path).resolve(strict=True)
    report=json.loads(report_path.read_text());result=set()
    with sqlite3.connect('file:'+str(Path(queue_path).resolve(strict=True))+'?mode=ro',uri=True) as db:
        for i,item in enumerate(report.get('accepted',[]),1):
            if item.get('sha256') in exclusions:result.add(i);continue
            if item.get('sha256'):continue
            path=report_path.parent/'clips'/f'clip_{i:02d}.mp4'
            if path.is_file():
                if not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() in exclusions:result.add(i)
                continue
            # No file/hash in legacy report: exact path + BOTH confirmed account
            # receipts must name the same specifically excluded hash.
            rows=db.execute('select account,sha256,status,video_id from tasks where path=?',(str(path),)).fetchall()
            for sha in exclusions:
                if set(a for a,s,status,v in rows if s==sha and status=='confirmed' and v)==set(ACCOUNTS):
                    result.add(i);break
    return result


def load_report_clips(report_path, queue_path, exclusions):
    import sqlite3
    report_path = Path(report_path)
    report = json.loads(report_path.read_text())
    if report.get('status') != 'complete': raise Blocked('review incomplete')
    clips = []
    excluded_indices=excluded_report_indices(report_path,queue_path,exclusions)
    with sqlite3.connect('file:'+str(Path(queue_path).resolve(strict=True))+'?mode=ro', uri=True) as db:
        for i, item in enumerate(report.get('accepted', []), 1):
            if i in excluded_indices:continue
            sha = item.get('sha256')
            if not sha: raise Blocked('review lacks exact clip hash')
            if sha in exclusions: continue
            path = report_path.parent/'clips'/f'clip_{i:02d}.mp4'
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != sha: raise Blocked('clip hash/path changed')
            videos = {}
            for account in ACCOUNTS:
                row = db.execute('select status,video_id from tasks where account=? and sha256=?', (account, sha)).fetchone()
                if not row or row[0] != 'confirmed' or not row[1]: raise Blocked('both library confirmations required')
                videos[account] = row[1]
            clips.append({'path': str(path.resolve()), 'sha256': sha, 'md5': hashlib.md5(path.read_bytes()).hexdigest(), 'videos': videos})
    return clips


def main():
    import argparse
    from .qianchuan_auth import load_service, verified_token
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report')
    parser.add_argument('--tag-intent',nargs=2,metavar=('ACCOUNT','SHA256'))
    parser.add_argument('--before-tags-json',help='Actual observed official UI labels, never infer [] from null')
    parser.add_argument('--tag-ui-evidence',help='Saved screenshot of exact account/video preflight')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    control = json.loads((root/'outputs/control_state.json').read_text())
    if control.get('workflow_hold') or control.get('status') == 'paused_by_user': raise Blocked('workflow held or paused')
    exclusions_path = Path(control['post_upload_exclusions'])
    exclusions = {x['sha256'] for x in json.loads(exclusions_path.read_text())['exclusions']}
    clips = load_report_clips(args.report, root/'data/library_upload/queue.sqlite3', exclusions)
    if not clips:
        print(json.dumps({'status': 'excluded_or_empty', 'writes': 0})); return
    runner=PostUpload(root/'data/post_upload/state.json',exclusions=exclusions)
    if args.tag_intent:
        account,sha=args.tag_intent
        if not any(c['sha256']==sha for c in clips):raise Blocked('tag target not in current report')
        before=json.loads(args.before_tags_json) if args.before_tags_json is not None else None
        row=runner.tag_intent(account,sha,before_tags=before,evidence_path=args.tag_ui_evidence)
        print(json.dumps({'status':'tag_intent_saved','account':account,'sha256':sha,'video_id':row['video_id'],'library_readback':row.get('library_readback')},ensure_ascii=False));return
    adapter = OfficialAdapter(verified_token(load_service(), ACCOUNTS))
    result = runner.process(clips, adapter)
    print(json.dumps({'status': result['status'], 'clip_count': len(clips)}))

if __name__ == '__main__':
    try:
        main()
    except Blocked as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc)}, ensure_ascii=False))
        raise SystemExit(2)
