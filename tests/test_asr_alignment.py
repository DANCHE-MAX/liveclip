import unittest
from liveclip.asr_alignment import verify_alignment, conservative_alignment, guard_adjacent_uncertainty
from liveclip.cloud_asr import build_alignment_prompt

class AlignmentTests(unittest.TestCase):
    def test_prompt_prioritizes_cloud_asr(self):
        prompt=build_alignment_prompt('宽松版型',[{'id':1,'start':0,'end':2,'text':'宽宫百姓'}])
        self.assertIn('不要输出本地错字',prompt)
        self.assertIn('宽松版型',prompt)
    def test_preserves_times_and_cloud_evidence(self):
        local=[{'id':1,'start':1,'end':3,'text':'一色'}]
        result=verify_alignment(local,'蓝色毛衣很宽松', [{'id':1,'text':'蓝色毛衣'}])
        self.assertEqual(result[0]['start'],1)
        self.assertEqual(result[0]['text'],'蓝色毛衣')
    def test_invented_quote_fails(self):
        with self.assertRaises(ValueError):
            verify_alignment([{'id':1,'start':1,'end':3}], '蓝色毛衣', [{'id':1,'text':'羊绒毛衣'}])
    def test_reorder_fails(self):
        with self.assertRaises(ValueError):
            verify_alignment([{'id':1,'start':1,'end':3},{'id':2,'start':3,'end':4}], '蓝色毛衣很宽松', [{'id':2,'text':'蓝色'},{'id':1,'text':'毛衣'}])
    def test_missing_segment_is_not_silently_preserved(self):
        with self.assertRaises(ValueError):
            verify_alignment([{'id':1,'start':1,'end':3},{'id':2,'start':3,'end':4}], '蓝色毛衣', [{'id':1,'text':'蓝色'}])
    def test_empty_correction_is_explicitly_uncertain(self):
        result=verify_alignment([{'id':1,'start':1,'end':3}], '蓝色毛衣', [{'id':1,'text':''}])
        self.assertTrue(result[0]['alignment_uncertain'])
    def test_unsupported_sentence_does_not_contaminate_other_times(self):
        local=[{'id':1,'start':1,'end':3},{'id':2,'start':3,'end':4}]
        result=conservative_alignment(local,'蓝色宽松',[{'id':1,'text':'红色'},{'id':2,'text':'宽松'}])
        self.assertTrue(result[0]['alignment_uncertain'])
        self.assertEqual(result[1]['text'],'宽松')
    def test_adjacent_segments_are_guarded_against_shift(self):
        rows=[{'id':1,'alignment_uncertain':False},{'id':2,'alignment_uncertain':True},{'id':3,'alignment_uncertain':False},{'id':4,'alignment_uncertain':False}]
        result=guard_adjacent_uncertainty(rows)
        self.assertEqual([x['alignment_uncertain'] for x in result],[True,True,True,False])
