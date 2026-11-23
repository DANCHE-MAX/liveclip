import hashlib,tempfile,unittest
from pathlib import Path
from liveclip.qianchuan_readback import lookup_membership, ApiFailure

class ReadbackTests(unittest.TestCase):
 def test_matching_video_in_plan_true(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'v.mp4';p.write_bytes(b'video');item={'account':'9000000000000003','plan':'9000000000000004','path':str(p)}
   def get(path,q):
    if path.endswith('video/get/'):return {'code':0,'data':{'list':[{'id':'video1','signature':hashlib.md5(b'video').hexdigest()}]}}
    return {'code':0,'data':{'ad_id':int(item['plan']),'programmatic_creative_media_list':{'video_material':[{'video_id':'video1'}]}}}
   self.assertIs(lookup_membership(item,get),True)
 def test_zero_video_is_not_confirmed_absence(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'v';p.write_bytes(b'video')
   self.assertIsNone(lookup_membership({'account':'a','plan':'p','path':str(p)},lambda a,b:{'code':0,'data':{'list':[]}}))
 def test_api_error_is_not_zero(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'v';p.write_bytes(b'v')
   with self.assertRaises(ApiFailure):lookup_membership({'account':'a','plan':'p','path':str(p)},lambda a,b:{'code':40100,'message':'frequency'})

class SafetyTests(unittest.TestCase):
 def test_unapproved_endpoint_is_not_requested(self):
  from liveclip.qianchuan_readback import OfficialReader
  r=OfficialReader(lambda:'token', lambda request: (_ for _ in ()).throw(AssertionError('network called')))
  with self.assertRaises(ValueError):r.get('/open_api/v1.0/anything/',{})

 def test_queue_reconciliation_checks_destination_and_file_integrity(self):
  import sqlite3
  from liveclip.qianchuan_readback import reconcile_queue
  from liveclip.upload_queue import UploadQueue
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'v';p.write_bytes(b'video');q=UploadQueue(Path(d)/'q.db')
   q.enqueue_file('9000000000000003','9000000000000004',p)
   with sqlite3.connect(q.path) as db:db.execute("UPDATE tasks SET status='uncertain'")
   class Reader:
    def get(self,path,params):
     if path.endswith('video/get/'):return {'code':0,'data':{'list':[{'id':'v1','signature':hashlib.md5(b'video').hexdigest()}]}}
     return {'code':0,'data':{'ad_id':9000000000000004,'programmatic_creative_media_list':{'video_material':[{'video_id':'v1'}]}}}
   p.write_bytes(b'changed')
   self.assertEqual(reconcile_queue(q,Reader())['uncertain'],1)
   p.write_bytes(b'video')
   self.assertEqual(reconcile_queue(q,Reader())['confirmed'],1)
