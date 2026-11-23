import tempfile, unittest
from pathlib import Path
from liveclip.plain_upload import PlainQueue

class PlainQueueTests(unittest.TestCase):
 def test_serial_cooldown_and_readback(self):
  with tempfile.TemporaryDirectory() as d:
   q=PlainQueue(Path(d)/'q.db');p=Path(d)/'v.mp4';p.write_bytes(b'v')
   for account in ('a','b'):
    for i in range(3):q.add(account,p,str(i))
   calls=[];clock=[100.0];sleeps=[]
   def upload(row):calls.append(row['account']);return {'code':0,'video_id':'v'}
   def sleep(n):sleeps.append(n);clock[0]+=n
   self.assertEqual(q.run(lambda r:False,upload,lambda r:True,now=lambda:clock[0],sleep=sleep,check_file=False),'complete')
   self.assertEqual(calls,['a']*3+['b']*3);self.assertEqual(sleeps,[5,5])
 def test_ambiguous_write_never_retries(self):
  with tempfile.TemporaryDirectory() as d:
   q=PlainQueue(Path(d)/'q.db');p=Path(d)/'v.mp4';p.write_bytes(b'v');q.add('a',p,'x');calls=[]
   def upload(r):calls.append(1);raise TimeoutError()
   self.assertEqual(q.run(lambda r:False,upload,lambda r:None,check_file=False),'paused_unverified')
   self.assertEqual(q.run(lambda r:False,upload,lambda r:None,check_file=False),'paused_unverified')
   self.assertEqual(len(calls),1)
 def test_rate_limit_stops(self):
  with tempfile.TemporaryDirectory() as d:
   q=PlainQueue(Path(d)/'q.db');p=Path(d)/'v.mp4';p.write_bytes(b'v');q.add('a',p,'x');q.add('a',p,'y');calls=[]
   def up(r):calls.append(1);return {'code':40100}
   self.assertEqual(q.run(lambda r:False,up,lambda r:None,check_file=False),'paused_rate_limit')
   self.assertEqual(len(calls),1)
