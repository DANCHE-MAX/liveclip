import unittest
from liveclip.paired_delivery import cleanup_ready


class PairedDeliveryTests(unittest.TestCase):
    def state(self):
        return {'required_accounts':['a','b'],'clips':[{'sha256':'clip','confirmed_accounts':['a','b']}],
                'archives':{kind:{'status':'sent','sha256':kind,'readback':{'recipient_verified':True,'filename_verified':True,'upload_complete':True,'no_failure_marker':True,'evidence_path':'proof'}} for kind in ('originals','highlights')}}

    def test_both_archives_and_both_accounts_required(self):
        s=self.state(); self.assertTrue(cleanup_ready(s))
        s['archives']['originals']['status']='sending'; self.assertFalse(cleanup_ready(s))
        s=self.state(); s['clips'][0]['confirmed_accounts']=['a']; self.assertFalse(cleanup_ready(s))

    def test_click_send_without_readback_never_allows_cleanup(self):
        s=self.state(); del s['archives']['originals']['readback']; self.assertFalse(cleanup_ready(s))
        s=self.state(); s['archives']['highlights']['readback']['upload_complete']=False
        self.assertFalse(cleanup_ready(s))

    def test_no_clips_or_duplicate_accounts_never_allow_cleanup(self):
        s=self.state(); s['clips']=[]; self.assertFalse(cleanup_ready(s))
        s=self.state(); s['required_accounts']=['a','a']; self.assertFalse(cleanup_ready(s))


if __name__=='__main__':unittest.main()

class FutureGateTests(unittest.TestCase):
    def test_future_state_cannot_clean_after_library_only(self):
        s=PairedDeliveryTests().state()
        s['post_upload_requirements']='tag_and_running_plans_v1'
        self.assertFalse(cleanup_ready(s))
    def test_unknown_requirement_never_allows_cleanup(self):
        s=PairedDeliveryTests().state();s['post_upload_requirements']='unknown'
        self.assertFalse(cleanup_ready(s))
    def test_build_refuses_missing_post_upload_ledger_before_packaging(self):
        from liveclip.paired_delivery import build_pair
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'pair'
            with self.assertRaisesRegex(ValueError,'post-upload'):
                build_pair([],[],Path(d)/'windows',Path(d)/'queue',target,post_upload_path=Path(d)/'missing')
            self.assertFalse(target.exists())

class ArchivePostUploadIntegrationTests(unittest.TestCase):
    def make_fixture(self, root):
        import hashlib,json,sqlite3
        from tests.test_post_upload import Adapter,ACCOUNTS
        from liveclip.post_upload import PostUpload
        (root/'clips').mkdir();p=root/'clips/clip_01.mp4';p.write_bytes(b'fixture')
        raw=root/'raw.mp4';raw.write_bytes(b'original');sha=hashlib.sha256(p.read_bytes()).hexdigest()
        reg=root/'registry.db';queue=root/'queue.db';ledger=root/'post.json'
        with sqlite3.connect(reg) as db:
            db.execute('create table windows(stream text,peak text,status text,path text,sha256 text)')
            db.execute('insert into windows values(?,?,?,?,?)',('stream','peak','complete',str(raw),hashlib.sha256(raw.read_bytes()).hexdigest()))
        with sqlite3.connect(queue) as db:
            db.execute('create table tasks(account text,sha256 text,status text,video_id text)')
            db.executemany('insert into tasks values(?,?,?,?)',[(a,sha,'confirmed',a+'video') for a in ACCOUNTS])
        report=root/'report.json';report.write_text(json.dumps({'status':'complete','source':str(raw),'source_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),
            'source_registration':[{'stream':'stream','peak':'peak'}],'accepted':[{'sha256':sha}]}))
        PostUpload(ledger,sleep=lambda _:None).process([{'path':str(p),'sha256':sha,'md5':hashlib.md5(p.read_bytes()).hexdigest(),'videos':{a:a+'video' for a in ACCOUNTS}}],Adapter())
        return report,reg,queue,ledger,sha
    def test_new_pair_contains_confirmed_post_upload_gate_and_zip_manifest(self):
        import tempfile,json,zipfile
        from pathlib import Path
        from unittest.mock import patch
        from liveclip.paired_delivery import build_pair
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);report,reg,queue,ledger,sha=self.make_fixture(root)
            with patch('liveclip.paired_delivery.media_probe',return_value={'audio':True,'video':True,'duration':20}):
                state=build_pair([report],[('stream','peak')],reg,queue,root/'pair',post_upload_path=ledger)
            self.assertEqual(state['post_upload_requirements'],'tag_and_running_plans_v1')
            self.assertFalse(cleanup_ready(state))
            for a in state['archives'].values():a.update(status='sent',readback={'recipient_verified':True,'filename_verified':True,'upload_complete':True,'no_failure_marker':True,'evidence_path':'verified'})
            self.assertTrue(cleanup_ready(state))
            with zipfile.ZipFile(root/'pair/highlights.zip') as z:
                self.assertEqual(json.loads(z.read('manifest.json'))['clips'][0]['post_upload']['sha256'],sha)
            state['clips'][0]['post_upload']['accounts']['9000000000000003']['tag']['status']='unknown'
            self.assertFalse(cleanup_ready(state))
    def test_extra_unmapped_original_rejected_before_zip_creation(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from liveclip.paired_delivery import build_pair
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);report,reg,queue,ledger,sha=self.make_fixture(root)
            with patch('liveclip.paired_delivery.media_probe',return_value={'audio':True,'video':True,'duration':20}):
                with self.assertRaisesRegex(ValueError,'Unmapped'):
                    build_pair([report],[('stream','peak'),('extra','peak')],reg,queue,root/'pair',post_upload_path=ledger)
            self.assertFalse((root/'pair').exists())
