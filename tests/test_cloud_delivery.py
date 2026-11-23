import tempfile,unittest
from pathlib import Path
from liveclip.cloud_delivery import deliver_cloud

class CloudDeliveryTests(unittest.TestCase):
 def test_stages_only_once_and_records_success(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'d.zip';p.write_bytes(b'zip');calls=[]
   def upload(x):calls.append('upload');return {'token':'file1','url':'https://example.com/file/1'}
   def check(x):calls.append('private');return True
   def grant(x,recipient):calls.append('grant');return True
   def send(url,recipient,key):calls.append('send');return 'msg1'
   args=(root/'state.db','2026-11-19',p,'recipient',upload,check,grant,send)
   self.assertEqual(deliver_cloud(*args),'sent');self.assertEqual(deliver_cloud(*args),'sent')
   self.assertEqual(calls,['upload','private','grant','send'])
 def test_unverified_permissions_prevent_share_and_send(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'d.zip';p.write_bytes(b'zip');calls=[]
   r=deliver_cloud(root/'db','2026-11-19',p,'recipient',lambda x:{'token':'f','url':'https://example.com'},lambda x:False,lambda *a:calls.append('grant'),lambda *a:calls.append('send'))
   self.assertEqual(r,'blocked');self.assertEqual(calls,[])
 def test_unknown_upload_never_retried(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'d.zip';p.write_bytes(b'zip');calls=[]
   def upload(x):calls.append('upload');raise TimeoutError()
   args=(root/'db','2026-11-19',p,'recipient',upload,lambda x:True,lambda *a:True,lambda *a:'m')
   self.assertEqual(deliver_cloud(*args),'uncertain');self.assertEqual(deliver_cloud(*args),'uncertain');self.assertEqual(len(calls),1)

class PrivacyTests(unittest.TestCase):
 def test_private_download_requires_closed_links_external_and_download(self):
  from liveclip.cloud_delivery import private_for_external_download
  good={'link_share_entity':'closed','external_access':True,'security_entity':'anyone_can_view','share_entity':'only_full_access'}
  self.assertTrue(private_for_external_download(good))
  for key,value in [('link_share_entity','tenant_readable'),('external_access',False),('security_entity','only_full_access'),('share_entity','anyone')]:
   self.assertFalse(private_for_external_download({**good,key:value}))
