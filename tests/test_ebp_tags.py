import unittest
from liveclip.ebp_tags import tag_status, build_add_payload

class TagTests(unittest.TestCase):
 def test_platform_nested_data(self):
  response={'code':0,'data':{'data':{'materials':[{'material_id':123,'tags':[]}],'errors':[]}}}
  self.assertIs(tag_status(response,123),False)
 def test_confirm_exact_custom_label(self):
  response={'code':0,'data':{'materials':[{'material_id':123,'tags':[{'tag_name':'切片','tag_type':'CUSTOM'}]}],'errors':[]}}
  self.assertIs(tag_status(response,123),True)
 def test_explicit_material_without_label_is_false(self):
  response={'code':0,'data':{'materials':[{'material_id':123,'tags':[]}],'errors':[]}}
  self.assertIs(tag_status(response,123),False)
 def test_failed_or_partial_response_is_unknown(self):
  for r in ({'code':40002},{'code':0,'data':{'materials':[]}}, {'code':0,'data':{'materials':[{'material_id':123,'tags':[]}],'errors':[{'material_id':123}]}}):
   self.assertIsNone(tag_status(r,123))
 def test_add_payload_is_additive_and_scoped(self):
  self.assertEqual(build_add_payload(9000000000000006,123),{'account_id':9000000000000006,'account_type':'EBP','material_ids':[123],'action':'ADD','custom_tag_names':['切片']})
  with self.assertRaises(ValueError):build_add_payload(3,123)
  with self.assertRaises(ValueError):build_add_payload(9000000000000006,0)
