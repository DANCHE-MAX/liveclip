"""Read-only, account-separated livestream clip supplement for the daily bot."""
import argparse
from datetime import date, datetime
import importlib.util
import json
from pathlib import Path
import sqlite3
import time
import urllib.parse
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
ACCOUNTS = [('9000000000000003', '示例账号A'),
            ('9000000000000001', '示例账号B')]
SERVICE = Path('config/local_qianchuan_service.py')


def accounts(root=ROOT):
    path=root/'config/clip_daily_accounts.json'
    if not path.exists():return ACCOUNTS
    value=json.loads(path.read_text())
    if not isinstance(value,list) or not value:raise ValueError('Missing report accounts')
    result=[(str(r['id']),r['name']) for r in value]
    if len({a for a,n in result})!=len(result) or any(not a.isdigit() or not isinstance(n,str) or not n.strip() for a,n in result):
        raise ValueError('Invalid or duplicate report accounts')
    return result


def new_count(rows, day):
    first = {}
    for row in rows:
        key = row['sha256']; value = row.get('first_confirmed')
        if value: first[key] = min(value, first.get(key, value))
    if any(r['sha256'] not in first for r in rows): return None
    return sum(value == day for value in first.values())


def rank(rows):
    eligible = []
    for row in rows:
        if any(row.get(k) is None for k in ('spend', 'gmv', 'orders')): continue
        if row['spend'] <= 0 or row['orders'] <= 0 or row['gmv'] <= 0: continue
        eligible.append(dict(row, roi=row['gmv']/row['spend']))
    return sorted(eligible, key=lambda r: (-r['roi'], -r['orders'], -r['gmv'], r['material_id']))[:3]


def registry(root=ROOT):
    with sqlite3.connect('file:'+str(root/'data/library_upload/queue.sqlite3')+'?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(r) for r in db.execute("SELECT * FROM tasks WHERE status='confirmed'")]
    material = {}; first = {}
    saved = root/'outputs/tag_scope_check_20261120/tag_final_readback.json'
    if saved.exists():
        for account in json.loads(saved.read_text())['accounts']:
            for item in account['materials']:
                material[(str(account['account']),str(item['id']))] = str(item['material_id'])
    logs = [root/'data/library_upload/audit.jsonl'] + list((root/'outputs').glob('qianchuan*/audit.jsonl'))
    for path in logs:
        if not path.exists(): continue
        for line in path.read_text().splitlines():
            event=json.loads(line); account=str(event.get('account','')); when=str(event.get('time',''))[:10]
            if event.get('event')=='upload_response' and event.get('code')==0 and event.get('material_id'):
                material[(account,str(event.get('video_id')))] = str(event['material_id'])
            verified = []
            if event.get('event')=='verified': verified=[str(event['video_id'])]
            if event.get('status') in ('verified','already_present'):
                verified=[str(x['id']) for x in event.get('matches',[])]
                for x in event.get('matches',[]):
                    if x.get('material_id'): material[(account,str(x['id']))]=str(x['material_id'])
            for video in verified:
                date.fromisoformat(when); key=(account,video)
                first[key]=min(when,first.get(key,when))
    for row in rows:
        key=(row['account'],str(row.get('video_id')))
        row.update(material_id=material.get(key),first_confirmed=first.get(key),name=Path(row['path']).name)
        path=Path(row['path']); review=path.parent.parent/'review_report.json'
        if review.exists() and path.stem.startswith('clip_'):
            try:
                item=json.loads(review.read_text())['accepted'][int(path.stem.split('_')[-1])-1]
                if item.get('product'):row['name']=item['product']+'｜'+path.parent.parent.name+'｜'+path.stem
            except (ValueError,KeyError,IndexError):pass
    return rows


class API:
    def __init__(self):
        spec=importlib.util.spec_from_file_location('clip_report_oauth',SERVICE)
        self.service=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.service)
        self.token=self.service._keychain_read(self.service.ACCESS_SERVICE)
        if not self.token: raise RuntimeError('missing_token')
        self.count=0

    def get(self, path, params):
        if self.count and self.count % 2 == 0: time.sleep(5)
        self.count+=1
        request=urllib.request.Request('https://api.oceanengine.com'+path+'?'+urllib.parse.urlencode(params),headers={'Access-Token':self.token})
        try:
            with urllib.request.urlopen(request,timeout=30) as response: result=json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError('api_429' if error.code==429 else 'http_'+str(error.code)) from None
        if result.get('code')!=0: raise RuntimeError('api_'+str(result.get('code')))
        return result

    def fetch(self, account, day, ids):
        self.service.ACCOUNT_ID=account
        code=self.service._probe_account().get('code')
        if code!=0: raise RuntimeError('probe_'+str(code))
        params=dict(advertiser_id=account,data_topic='OVERALL_ROI_LIVE_MATERIAL_VIDEO',data_period='OVER_ALL_DATA',
            dimensions=json.dumps(['material_id','roi2_material_video_name']),
            metrics=json.dumps(['stat_cost_for_roi2','total_pay_order_gmv_for_roi2','total_pay_order_count_for_roi2']),
            filters=json.dumps([{'field':'roi2_material_type_v3','operator':7,'values':['3']}, {'field':'material_id','operator':7,'values':ids}]),
            start_time=day+' 00:00:00',end_time=day+' 23:59:59',page_size=100,order_by='[]')
        rows=[]; requests=[]; expected=None
        for page in range(1,101):
            result=self.get('/open_api/v1.0/qianchuan/report/uni_promotion/data/get/',dict(params,page=page))
            requests.append(result.get('request_id')); data=result['data']; info=data['page_info'];expected=info['total_number']
            for raw in data['rows']:
                flat={k:v.get('Value') for part in ('dimensions','metrics') for k,v in raw[part].items()}
                mid=str(flat['material_id'])
                if mid not in ids: raise ValueError('Unexpected material scope')
                rows.append(dict(material_id=mid,name=flat['roi2_material_video_name'],
                    spend=flat.get('stat_cost_for_roi2'),gmv=flat.get('total_pay_order_gmv_for_roi2'),orders=flat.get('total_pay_order_count_for_roi2')))
            if page>=info['total_page']: break
        if len(rows)!=expected or len({r['material_id'] for r in rows})!=len(rows): raise ValueError('Incomplete pagination')
        return rows, requests


def collect(day, root=ROOT, api=None):
    date.fromisoformat(day); known=registry(root)
    report=dict(date=day,new_count=new_count(known,day),accounts=[],collected_at=datetime.now().astimezone().isoformat(),
        count_basis='first_confirmed_library_upload_unique_sha256',ranking_basis='positive_orders_and_spend_then_payment_roi_desc',readonly=True)
    api=api or API(); stopped=False
    for account,name in accounts(root):
        entry=dict(account=account,name=name,complete=False,top=[]);report['accounts'].append(entry)
        scoped=[r for r in known if r['account']==account and (not r.get('first_confirmed') or r['first_confirmed']==day)]
        if stopped: entry['error']='previous_account_rate_limited';continue
        if any(not r.get('material_id') or not r.get('first_confirmed') for r in scoped):entry['error']='material_mapping_or_date_missing';continue
        ids=sorted({r['material_id'] for r in scoped});entry['registered_material_count']=len(ids)
        if not ids: entry.update(complete=True,rows=[],top=[],missing_material_ids=[]);continue
        try:
            rows,requests=api.fetch(account,day,ids)
            names={r['material_id']:r['name'] for r in scoped}
            for row in rows:
                row['platform_name']=row['name'];row['name']=names.get(row['material_id'],row['name'])
            entry.update(complete=True,rows=rows,top=rank(rows),request_ids=requests,
                         missing_material_ids=sorted(set(ids)-{r['material_id'] for r in rows}))
        except Exception as error:
            entry['error']=str(error) if isinstance(error,RuntimeError) else type(error).__name__
            stopped=entry['error'] in ('api_40100','api_429')
    return report


def render(report):
    count=report['new_count']; lines=['直播切片日报｜'+report['date'],
        '昨日新增独立切片：'+(str(count)+' 条' if count is not None else '待核验（上传确认时间记录不完整）')+'。同片跨账号上传只计一次。',
        '效果范围：各账号昨日新增入库切片在昨日完整日的表现；按支付 ROI 排序，仅纳入有消耗且有成交的素材。']
    for account in report['accounts']:
        lines.append(account['name']+'：')
        if not account['complete']:
            lines.append('效果待核验（'+account.get('error','unknown')+'），不输出榜单。');continue
        lines.append('昨日新增入库 %d 条。'%account.get('registered_material_count',0))
        if not account['top']:lines.append('暂无足够的已核验成交样本形成有效 Top 3；不把未返回的素材数据当作零。')
        elif account.get('missing_material_ids'):lines.append('以下仅为已返回指标中的暂列 Top 3，素材指标存在缺失，非完整榜单。')
        for index,row in enumerate(account['top'],1):
            lines.append('%d. %s（素材 %s）：消耗 %.2f 元，成交 %.2f 元，%s 单，支付 ROI %.2f%s。' %
                (index,row['name'],row['material_id'],row['spend'],row['gmv'],row['orders'],row['roi'],'；小样本观察' if row['orders']<3 else ''))
        missing=account.get('missing_material_ids',[])
        if missing:lines.append('%d 条登记素材未返回指标，状态待核验。'%len(missing))
    lines.append('目前覆盖 %d 个已配置账号；新增账号完成配置和授权后再纳入。支付 ROI 不代表结算利润。'%len(report['accounts']))
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--day',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); result=collect(args.day);args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'clips.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (args.output/'clips.txt').write_text(render(result));print(render(result))

if __name__=='__main__':main()
