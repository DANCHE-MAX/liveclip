import json
import tempfile
import unittest
from pathlib import Path
from liveclip.post_upload import PostUpload, Blocked, proof_valid

ACCOUNTS=['9000000000000003','9000000000000001']

class Adapter:
    def __init__(self):
        self.tags=['切片','旧标签']; self.ids=['old']; self.writes=0
        self.running=True; self.unknown=False; self.drop_old=False
    def video(self, clip, account):return {'id':account+'video','tags':self.tags,'signature':clip['md5'],'request_id':'tags-read'}
    def running_plans(self, account):return [{'id':'plan','status':'DELIVERY_OK','opt_status':'ENABLE','marketing_goal':'LIVE_PROM_GOODS'}] if self.running else []
    def detail(self, account, plan):return {'ad_id':plan,'status':'DELIVERY_OK','opt_status':'ENABLE','marketing_goal':'LIVE_PROM_GOODS','ids':list(self.ids),'request_id':'detail-read'}
    def cover(self,clip,account):return 'cover'
    def append(self, account, plan, video, cover):
        self.writes+=1
        if self.unknown:raise TimeoutError()
        if self.drop_old:self.ids=[]
        self.ids.append(video)
        return {'code':0,'request_id':'write'}

class PostUploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.file=self.root/'clip.mp4';self.file.write_bytes(b'fixture')
        import hashlib
        self.sha=hashlib.sha256(b'fixture').hexdigest()
        self.clip={'path':str(self.file),'sha256':self.sha,'md5':hashlib.md5(b'fixture').hexdigest(),
                   'videos':{a:a+'video' for a in ACCOUNTS}}
        self.state=self.root/'state.json';self.a=Adapter()
    def run_queue(self,exclude=()):
        return PostUpload(self.state,ACCOUNTS,exclude,sleep=lambda _:None).process([self.clip],self.a)
    def test_excluded_hash_never_reads_or_writes_even_when_file_gone(self):
        self.file.unlink()
        self.a.video=lambda *args: self.fail('manual 15 must not be queried')
        self.assertEqual(self.run_queue([self.sha])['excluded'],[self.sha]);self.assertEqual(self.a.writes,0)
    def test_missing_tag_stops_before_plan_write(self):
        self.a.tags=[]
        with self.assertRaisesRegex(Blocked,'tag'):self.run_queue()
        self.assertEqual(self.a.writes,0)
    def test_no_running_plan_never_means_complete(self):
        self.a.running=False
        with self.assertRaisesRegex(Blocked,'running'):self.run_queue()
        self.assertEqual(self.a.writes,0)
    def test_success_keeps_old_ids_and_rerun_never_appends_twice(self):
        state=self.run_queue();proof=state['clips'][self.sha]
        self.assertTrue(proof_valid(proof,ACCOUNTS,self.sha,self.clip['videos']))
        self.assertIn('old',self.a.ids);self.assertEqual(self.a.writes,2)
        self.run_queue();self.assertEqual(self.a.writes,2)
    def test_unknown_write_never_repeats_and_can_only_reconcile_present(self):
        self.a.unknown=True
        with self.assertRaises(Blocked):self.run_queue()
        self.a.unknown=False
        with self.assertRaisesRegex(Blocked,'uncertain'):self.run_queue()
        self.assertEqual(self.a.writes,1)
        self.a.ids.append(ACCOUNTS[0]+'video')
        self.run_queue();self.assertEqual(self.a.writes,2)
    def test_loss_of_existing_material_blocks(self):
        self.a.drop_old=True
        with self.assertRaisesRegex(Blocked,'retained'):self.run_queue()
    def test_changed_file_never_writes(self):
        self.file.write_bytes(b'changed')
        with self.assertRaisesRegex(Blocked,'hash'):self.run_queue()
        self.assertEqual(self.a.writes,0)
    def test_proof_requires_every_plan_and_exact_account_video(self):
        proof=self.run_queue()['clips'][self.sha]
        proof['accounts'][ACCOUNTS[0]]['plans']['plan']['status']='uncertain'
        self.assertFalse(proof_valid(proof,ACCOUNTS,self.sha,self.clip['videos']))

if __name__=='__main__':unittest.main()

class ContractTests(unittest.TestCase):
    def test_running_plan_inventory_queries_both_scenes_and_excludes_stopped(self):
        from liveclip.post_upload import OfficialAdapter
        class Fake(OfficialAdapter):
            def __init__(self):self.calls=[]
            def _request(self,path,params,**kw):
                self.calls.append((path,params))
                rows=[{'ad_info':{'id':params['adlab_scene'],'adlab_scene':params['adlab_scene'],
                      'marketing_goal':'LIVE_PROM_GOODS','status':'DELIVERY_OK' if params['adlab_scene']=='OVERALL_PROJECT' else 'LIVE_ROOM_OFF','opt_status':'ENABLE'}}]
                return {'data':{'ad_list':rows,'page_info':{'page':1,'total_page':1,'total_num':1}}}
        api=Fake();plans=api.running_plans(ACCOUNTS[0])
        self.assertEqual([p['id'] for p in plans],['OVERALL_PROJECT'])
        self.assertEqual([p['adlab_scene'] for _,p in api.calls],['OVERALL_PROJECT','UNI_PROJECT'])
    def test_missing_pagination_never_means_no_running_plans(self):
        from liveclip.post_upload import OfficialAdapter
        api=OfficialAdapter('not-a-real-token');api._request=lambda *a,**k:{'data':{'ad_list':[]}}
        with self.assertRaisesRegex(Blocked,'pagination'):api.running_plans(ACCOUNTS[0])
    def test_plan_append_body_only_contains_additive_video_fields(self):
        from liveclip.post_upload import OfficialAdapter
        api=OfficialAdapter('unused');calls=[]
        api._request=lambda *a,**k:calls.append((a,k)) or {'code':0}
        api.append(ACCOUNTS[0],'123','video','cover')
        self.assertEqual(calls[0][0][0],'/open_api/v1.0/qianchuan/uni_promotion/ad/material/add/')
        self.assertEqual(calls[0][1]['body'],{'advertiser_id':int(ACCOUNTS[0]),'ad_id':123,
            'programmatic_creative_media_list':{'video_material':[{'video_id':'video','image_mode':'VIDEO_VERTICAL','video_cover_id':'cover'}]}})
    def test_stops_if_plan_paused_between_inventory_and_write(self):
        with tempfile.TemporaryDirectory() as d:
            import hashlib
            p=Path(d)/'clip';p.write_bytes(b'x');api=Adapter();api.detail=lambda *a:{'ad_id':'plan','status':'USER_DISABLE','opt_status':'DISABLE','marketing_goal':'LIVE_PROM_GOODS','ids':[]}
            c={'path':str(p),'sha256':hashlib.sha256(b'x').hexdigest(),'md5':'m','videos':{a:a+'video' for a in ACCOUNTS}}
            with self.assertRaisesRegex(Blocked,'no longer running'):PostUpload(Path(d)/'state').process([c],api)
            self.assertEqual(api.writes,0)
    def test_api_error_message_is_saved_and_never_retries(self):
        with tempfile.TemporaryDirectory() as d:
            import hashlib
            p=Path(d)/'clip';p.write_bytes(b'x');api=Adapter();api.append=lambda *a:{'code':40000,'message':'specific reason','request_id':'req'}
            c={'path':str(p),'sha256':hashlib.sha256(b'x').hexdigest(),'md5':'m','videos':{a:a+'video' for a in ACCOUNTS}}
            state=Path(d)/'state';runner=PostUpload(state,sleep=lambda _:None)
            with self.assertRaises(Blocked):runner.process([c],api)
            result=json.loads(state.read_text())['clips'][c['sha256']]['accounts'][ACCOUNTS[0]]['plans']['plan']
            self.assertEqual(result['response']['message'],'specific reason')
            with self.assertRaisesRegex(Blocked,'uncertain'):runner.process([c],api)

class TagIntentTests(unittest.TestCase):
    def test_uncertain_tag_intent_cannot_be_submitted_again(self):
        with tempfile.TemporaryDirectory() as d:
            import hashlib
            p=Path(d)/'clip';p.write_bytes(b'x');api=Adapter();api.tags=[]
            sha=hashlib.sha256(b'x').hexdigest();state=Path(d)/'state'
            c={'path':str(p),'sha256':sha,'md5':'m','videos':{a:a+'video' for a in ACCOUNTS}}
            runner=PostUpload(state,sleep=lambda _:None)
            with self.assertRaises(Blocked):runner.process([c],api)
            runner.tag_intent(ACCOUNTS[0],sha)
            with self.assertRaisesRegex(Blocked,'uncertain'):runner.process([c],api)
            with self.assertRaises(Blocked):runner.tag_intent(ACCOUNTS[0],sha)
            self.assertEqual(api.writes,0)
            api.tags=['切片'];result=runner.process([c],api)
            self.assertTrue(proof_valid(result['clips'][sha],ACCOUNTS,sha,c['videos']))

class NullTagTests(unittest.TestCase):
    def test_null_needs_actual_ui_evidence_before_tag_intent(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'clip';p.write_bytes(b'x');sha=hashlib.sha256(b'x').hexdigest()
            c={'path':str(p),'sha256':sha,'md5':'m','videos':{a:a+'video' for a in ACCOUNTS}}
            api=Adapter();api.tags=None;runner=PostUpload(root/'state',sleep=lambda _:None)
            with self.assertRaisesRegex(Blocked,'tag'):runner.process([c],api)
            with self.assertRaises(Blocked):runner.tag_intent(ACCOUNTS[0],sha)
            proof=root/'ui.png';proof.write_bytes(b'UI evidence fixture')
            runner.tag_intent(ACCOUNTS[0],sha,before_tags=['existing'],evidence_path=proof)
            api.tags=['existing','切片']
            self.assertEqual(runner.process([c],api)['status'],'complete')

class LegacyExclusionTests(unittest.TestCase):
    def test_deleted_manual_report_without_embedded_hash_uses_exact_queue_mapping(self):
        import sqlite3
        from liveclip.post_upload import load_report_clips,excluded_report_indices
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);report=root/'review.json';report.write_text(json.dumps({'status':'complete','accepted':[{}]}))
            queue=root/'queue';path=root/'clips/clip_01.mp4'
            with sqlite3.connect(queue) as db:
                db.execute('create table tasks(account text,path text,sha256 text,status text,video_id text)')
                db.executemany('insert into tasks values(?,?,?,?,?)',[(a,str(path.resolve()),'manual','confirmed',a+'video') for a in ACCOUNTS])
            self.assertEqual(excluded_report_indices(report,queue,{'manual'}),{1})
            self.assertEqual(load_report_clips(report,queue,{'manual'}),[])
            with self.assertRaises(Blocked):load_report_clips(report,queue,set())
