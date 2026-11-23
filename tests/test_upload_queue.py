import tempfile,unittest
from pathlib import Path
from liveclip.upload_queue import UploadQueue, RateLimited

class UploadQueueTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.q=UploadQueue(Path(self.tmp.name)/'queue.db');self.clock=[100.0];self.sleeps=[]
 def tearDown(self):self.tmp.cleanup()
 def test_serial_two_then_five_and_two_accounts(self):
  for account in ('a','b'):
   for i in range(3):self.q.enqueue(account,'p',f'file{i}',f'hash{i}')
  calls=[]
  def lookup(item):return False
  def submit(item):calls.append(item['account']);return 'ok'
  def sleep(n):self.sleeps.append(n);self.clock[0]+=n
  result=self.q.run(lookup,submit,verify=lambda i:True,now=lambda:self.clock[0],sleep=sleep)
  self.assertEqual(result,'complete');self.assertEqual(calls,['a']*3+['b']*3);self.assertEqual(self.sleeps,[5,5])
 def test_rate_limit_pauses_and_rechecks_without_retry(self):
  self.q.enqueue('a','p','v','h'); calls=[]; checks=[]
  def lookup(item): checks.append(1);return False
  def submit(item):calls.append(1);raise RateLimited()
  self.assertEqual(self.q.run(lookup,submit,verify=lookup,now=lambda:100,sleep=lambda _:None),'paused_rate_limit')
  self.assertEqual(len(calls),1);self.assertEqual(len(checks),2)
  self.assertEqual(self.q.statuses(),['uncertain'])
 def test_already_present_skips_submission(self):
  self.q.enqueue('a','p','v','h');calls=[]
  self.assertEqual(self.q.run(lambda i:True,lambda i:calls.append(i),verify=lambda i:True,now=lambda:100,sleep=lambda _:None),'complete')
  self.assertEqual(calls,[])
 def test_unknown_status_never_resubmits(self):
  self.q.enqueue('a','p','v','h'); calls=[]
  self.assertEqual(self.q.run(lambda i:None,lambda i:calls.append(i),verify=lambda i:None,now=lambda:100,sleep=lambda _:None),'paused_unverified')
  self.assertEqual(calls,[])

class StagingTests(unittest.TestCase):
 def test_stage_only_complete_rendered_clips_for_both_accounts(self):
  import json
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'clips').mkdir();(root/'clips'/'clip_01.mp4').write_bytes(b'one')
   report=root/'review_report.json';report.write_text(json.dumps({'status':'complete','accepted':[{'start':0,'end':15}]}))
   q=UploadQueue(root/'queue.db');q.stage_report(report,[('a','1'),('b','2')]);self.assertEqual(q.statuses(),['pending','pending'])
 def test_unverified_report_rejected(self):
  import json
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);report=root/'report.json';report.write_text(json.dumps({'status':'needs_transcript_review','accepted':[]}))
   q=UploadQueue(root/'queue.db')
   with self.assertRaises(ValueError):q.stage_report(report,[('a','1')])

class OrderTests(unittest.TestCase):
 def test_interleaved_enqueues_still_process_accounts_serially(self):
  with tempfile.TemporaryDirectory() as d:
   q=UploadQueue(Path(d)/'queue.db')
   for h in ('x','y'):
    q.enqueue('a','p',h,h);q.enqueue('b','p',h,h)
   calls=[];q.run(lambda _:False,lambda x:calls.append(x['account']),lambda _:True,now=lambda:100,sleep=lambda _:None)
   self.assertEqual(calls,['a','a','b','b'])

class FileIntegrityTests(unittest.TestCase):
 def test_changed_file_pauses_before_network(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'clip.mp4';p.write_bytes(b'initial');q=UploadQueue(Path(d)/'q.db');q.enqueue_file('a','p',p);p.write_bytes(b'changed');calls=[]
   self.assertEqual(q.run(lambda i:calls.append('lookup'),lambda i:calls.append('write'),lambda i:True),'paused_file_changed');self.assertEqual(calls,[])

class ReconcileTests(unittest.TestCase):
 def test_readback_confirms_uncertain_without_reupload(self):
  with tempfile.TemporaryDirectory() as d:
   q=UploadQueue(Path(d)/'queue.db');q.enqueue('a','p','file','h')
   self.assertEqual(q.run(lambda _:False,lambda _:(_ for _ in ()).throw(RateLimited()),lambda _:None),'paused_rate_limit')
   self.assertEqual(q.reconcile(lambda _:True),{'confirmed':1,'uncertain':0});self.assertEqual(q.statuses(),['confirmed'])
