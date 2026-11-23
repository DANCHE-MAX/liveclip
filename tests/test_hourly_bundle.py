import hashlib,json,sqlite3,tempfile,unittest,zipfile
from pathlib import Path
from liveclip.hourly_bundle import bundle_windows

class HourlyBundleTests(unittest.TestCase):
 def test_reused_window_appears_once_and_preserves_source(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'source.mp4';p.write_bytes(b'video');sha=hashlib.sha256(b'video').hexdigest()
   db=root/'windows.db'
   with sqlite3.connect(db) as c:
    c.execute('create table windows(stream text,peak text,status text,path text,sha256 text)')
    c.executemany('insert into windows values(?,?,?,?,?)',[('s','one','complete',str(p),sha),('s','two','complete',str(p),sha)])
   output=root/'hour.zip';result=bundle_windows(db,[('s','one'),('s','two')],output)
   self.assertEqual(result['count'],1);self.assertTrue(p.exists())
   with zipfile.ZipFile(output) as z:self.assertIsNone(z.testzip());self.assertEqual(len([x for x in z.namelist() if x.endswith('.mp4')]),1)
 def test_pending_or_changed_window_never_produces_zip(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'source.mp4';p.write_bytes(b'video');db=root/'windows.db'
   with sqlite3.connect(db) as c:
    c.execute('create table windows(stream text,peak text,status text,path text,sha256 text)')
    c.execute('insert into windows values(?,?,?,?,?)',('s','one','pending',str(p),'bad'))
   with self.assertRaises(ValueError):bundle_windows(db,[('s','one')],root/'hour.zip')
   self.assertFalse((root/'hour.zip').exists())
