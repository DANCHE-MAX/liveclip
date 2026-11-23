import unittest
from liveclip.cloud_asr import failed_alignment
from liveclip.policy import validate_candidate

class FailedAlignmentTests(unittest.TestCase):
    def test_failed_chunk_preserves_timing_but_cannot_be_selected(self):
        rows=failed_alignment([{'id':3,'start':10,'end':25,'text':'错误猜测'}])
        self.assertEqual(rows[0]['text'],'')
        self.assertEqual((rows[0]['id'],rows[0]['start'],rows[0]['end']),(3,10,25))
        with self.assertRaisesRegex(ValueError,'Uncertain'):
            validate_candidate({'first_id':3,'last_id':3,'kind':'product_explanation','product':'外套','complete':True},rows,360)

if __name__=='__main__':unittest.main()
