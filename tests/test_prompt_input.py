import unittest
from liveclip.prompts import compact_segments

class PromptInputTests(unittest.TestCase):
    def test_only_review_fields_are_sent(self):
        raw=[{'id':0,'start':1,'end':3,'text':'讲解','words':[{'word':'讲解'}], 'alignment_uncertain':True}]
        self.assertEqual(compact_segments(raw),[{'id':0,'start':1,'end':3,'text':'讲解','alignment_uncertain':True}])
