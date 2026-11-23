import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from liveclip.download_registry import DownloadRegistry, DownloadBlocked

class RegistryTests(unittest.TestCase):
 def test_finish_archives_original_and_registry_reuses_saved_path(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder).resolve();source=root/'download.mp4';source.write_bytes(b'original')
   registry=DownloadRegistry(root/'registry.db', originals_dir=root/'keep')
   registry.reserve('s','2026-11-20T09:01:00+08:00')
   saved=registry.finish('s','2026-11-20T09:01:00+08:00',source)
   self.assertEqual(saved,root/'keep/download.mp4');self.assertEqual(saved.read_bytes(),b'original')
   self.assertFalse(source.exists())
   self.assertEqual(registry.reserve('s','2026-11-20T09:01:00+08:00')['path'],str(saved))
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.r=DownloadRegistry(self.root/'downloads.sqlite3'); self.v=self.root/'video.mp4'; self.v.write_bytes(b'video')
 def tearDown(self): self.tmp.cleanup()
 def test_first_acquires_then_reuses_same_peak(self):
  download=Mock(return_value=self.v)
  self.assertEqual(self.r.acquire_once('stream','2026-11-18T15:43:00+08:00',download),self.v.resolve())
  self.assertEqual(self.r.acquire_once('stream','2026-11-18T07:43:00+00:00',download),self.v.resolve())
  self.assertEqual(download.call_count,1)
 def test_missing_or_changed_file_never_triggers_redownload(self):
  self.r.register_existing('stream','2026-11-18T15:43:00+08:00',self.v)
  self.v.write_bytes(b'changed'); download=Mock()
  with self.assertRaises(DownloadBlocked): self.r.acquire_once('stream','2026-11-18T15:43:00+08:00',download)
  download.assert_not_called()
 def test_failed_download_remains_blocked(self):
  download=Mock(side_effect=RuntimeError('unknown result'))
  with self.assertRaises(RuntimeError): self.r.acquire_once('stream','2026-11-18T15:43:00+08:00',download)
  with self.assertRaises(DownloadBlocked): self.r.acquire_once('stream','2026-11-18T15:43:00+08:00',download)
  self.assertEqual(download.call_count,1)
 def test_distinct_stream_and_peak_do_not_collide(self):
  download=Mock(return_value=self.v)
  self.r.acquire_once('one','2026-11-18T15:43:00+08:00',download)
  self.r.acquire_once('two','2026-11-18T15:43:00+08:00',download)
  self.r.acquire_once('one','2026-11-18T15:44:00+08:00',download)
  self.assertEqual(download.call_count,3)
 def test_naive_time_rejected(self):
  with self.assertRaises(ValueError): self.r.acquire_once('one','2026-11-18T15:43:00',Mock())

class CliTests(unittest.TestCase):
 def test_cli_reserve_reuses_existing(self):
  import subprocess, json, sys
  with tempfile.TemporaryDirectory() as d:
   db=Path(d)/'reg.sqlite3'; f=Path(d)/'v.mp4'; f.write_bytes(b'video')
   DownloadRegistry(db).register_existing('s','2026-11-18T15:43:00+08:00',f)
   p=subprocess.run([sys.executable,'-m','liveclip.download_registry','--db',str(db),'reserve','s','2026-11-18T15:43:00+08:00'],capture_output=True,text=True,check=True)
   self.assertEqual(json.loads(p.stdout)['status'],'reuse')

class DailyRegistryTests(unittest.TestCase):
 def test_reservations_enforce_daily_66_minutes_and_reuse(self):
  import tempfile
  from pathlib import Path
  from liveclip.download_registry import DownloadRegistry
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);registry=DownloadRegistry(root/'registry.db');p=root/'old.mp4';p.write_bytes(b'old')
   peak='2026-11-19T12:00:00+08:00';registry.register_existing('old',peak,p)
   self.assertEqual(registry.reserve_daily('old',peak,'2026-11-20')['status'],'reuse')
   for i in range(11):self.assertEqual(registry.reserve_daily(str(i),peak,'2026-11-20')['status'],'reserved')
   with self.assertRaises(Exception):registry.reserve_daily('over',peak,'2026-11-20')
   self.assertEqual(registry.reserve_daily('tomorrow',peak,'2026-11-21')['status'],'reserved')
