"""Read-only membership checks for official Qianchuan endpoints."""
import hashlib
from pathlib import Path

class ApiFailure(RuntimeError):
    def __init__(self,code):
        super().__init__('qianchuan API returned code '+str(code)); self.code=code


def _ok(result):
    if not isinstance(result,dict) or result.get('code')!=0:
        raise ApiFailure(result.get('code') if isinstance(result,dict) else 'invalid')
    if not isinstance(result.get('data'),dict):raise ApiFailure('missing_data')
    return result['data']


def lookup_membership(item,get):
    """True if asset is configured; None on absence or ambiguous visibility.

    Empty search results do not establish absence because uploads can be delayed.
    get(path, params) must use the official API and protect credentials.
    """
    h=hashlib.md5()
    with Path(item['path']).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    signature=h.hexdigest()
    data=_ok(get('/open_api/v1.0/qianchuan/video/get/',{'advertiser_id':item['account'],'filtering':{'signatures':[signature]},'page':1,'page_size':100}))
    rows=data.get('list')
    if not isinstance(rows,list):return None
    page=data.get('page_info') or {}
    if page.get('total_page',1)>1:return None
    ids={x.get('id') for x in rows if x.get('signature')==signature and x.get('id')}
    if not ids:return None
    detail=_ok(get('/open_api/v1.0/qianchuan/uni_promotion/ad/detail/',{'advertiser_id':item['account'],'ad_id':item['plan']}))
    if str(detail.get('ad_id'))!=str(item['plan']):return None
    creative=detail.get('programmatic_creative_media_list')
    if not isinstance(creative,dict) or not isinstance(creative.get('video_material'),list):return None
    if any(x.get('video_id') in ids for x in creative['video_material']):return True
    return None

class OfficialReader:
    ALLOWED={'/open_api/v1.0/qianchuan/video/get/','/open_api/v1.0/qianchuan/uni_promotion/ad/detail/'}
    def __init__(self,token_provider,open_request):
        self.token_provider=token_provider;self.open_request=open_request
    def get(self,path,params):
        import json,urllib.parse,urllib.request
        if path not in self.ALLOWED:raise ValueError('Endpoint not approved for this reader')
        args={k:(json.dumps(v,ensure_ascii=False,separators=(',',':')) if isinstance(v,(dict,list)) else str(v)) for k,v in params.items()}
        request=urllib.request.Request('https://api.oceanengine.com'+path+'?'+urllib.parse.urlencode(args),headers={'Access-Token':self.token_provider()})
        return self.open_request(request)


DESTINATIONS = {
    '9000000000000003': '9000000000000004',
    '9000000000000001': '9000000000000002',
}


def reconcile_queue(queue, reader):
    """Resolve uncertain tasks only when the exact file is in its approved plan."""
    def lookup(item):
        if DESTINATIONS.get(item['account']) != item['plan']:
            return None
        h = hashlib.sha256()
        with Path(item['path']).open('rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                h.update(chunk)
        if h.hexdigest() != item['sha256']:
            return None
        return lookup_membership(item, reader.get)
    return queue.reconcile(lookup)
