import tempfile, unittest, sqlite3
from pathlib import Path
from liveclip.material_staging import MaterialStaging, ACCOUNTS

class MaterialStagingTests(unittest.TestCase):
 def test_stages_each_unique_file_for_both_accounts_with_required_tag(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'clip.mp4';p.write_bytes(b'video');q=MaterialStaging(Path(d)/'q.sqlite')
   q.stage([p,p]);q.stage([p]);rows=q.list_tasks()
   self.assertEqual(len(rows),2)
   self.assertEqual({r['account'] for r in rows},set(ACCOUNTS))
   self.assertTrue(all(r['label']=='切片' and r['status']=='pending_review' for r in rows))
 def test_batch_checks_all_files_before_staging(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'clip.mp4';p.write_bytes(b'video');q=MaterialStaging(Path(d)/'q.sqlite')
   with self.assertRaises((FileNotFoundError,ValueError)):q.stage([p,Path(d)/'missing.mp4'])
   self.assertEqual(q.list_tasks(),[])
 def test_existing_plan_queue_has_no_authority_to_mark_reviewed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'clip.mp4';p.write_bytes(b'video');q=MaterialStaging(Path(d)/'q.sqlite');q.stage([p])
   with sqlite3.connect(q.path) as db:self.assertEqual(db.execute("select distinct status from material_tasks").fetchall(),[('pending_review',)])
