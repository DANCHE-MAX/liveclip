import hashlib,json,sqlite3,tempfile,unittest,zipfile
from pathlib import Path
from liveclip.delivery_cleanup import cleanup_completed_batch

class CleanupTests(unittest.TestCase):
 def make_batch(self,root):
  folder=root/'batch';folder.mkdir();p=folder/'clip.mp4';p.write_bytes(b'clip')
  digest=hashlib.sha256(b'clip').hexdigest();archive=folder/'pack.zip'
  with zipfile.ZipFile(archive,'w') as z:
   z.write(p,'01_clip.mp4');z.writestr('manifest.json',json.dumps({'clips':[{'source':str(p),'sha256':digest,'name':'01_clip.mp4'}]}))
  return folder,p,archive,digest
 def test_uploads_and_delivery_required_before_cleanup(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);folder,p,archive,sha=self.make_batch(root)
   result=cleanup_completed_batch(folder,archive,{'a':set(),'b':{sha}},'sent',expected_accounts=('a','b'))
   self.assertEqual(result,'blocked');self.assertTrue(p.exists());self.assertTrue(archive.exists())
 def test_uncertain_delivery_never_deletes(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);folder,p,archive,sha=self.make_batch(root)
   self.assertEqual(cleanup_completed_batch(folder,archive,{'a':{sha},'b':{sha}},'uncertain',expected_accounts=('a','b')),'blocked')
   self.assertTrue(p.exists())
 def test_complete_batch_removes_only_verified_generated_files(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);folder,p,archive,sha=self.make_batch(root);source=root/'source.mp4';source.write_bytes(b'source')
   self.assertEqual(cleanup_completed_batch(folder,archive,{'a':{sha},'b':{sha}},'sent',expected_accounts=('a','b')),'complete')
   self.assertFalse(p.exists());self.assertFalse(archive.exists());self.assertTrue(source.exists())
 def test_changed_file_never_deletes_anything(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);folder,p,archive,sha=self.make_batch(root);p.write_bytes(b'changed')
   self.assertEqual(cleanup_completed_batch(folder,archive,{'a':{sha},'b':{sha}},'sent',expected_accounts=('a','b')),'blocked')
   self.assertTrue(p.exists());self.assertTrue(archive.exists())
