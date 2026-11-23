import unittest
from liveclip.semantic_retry import select_valid

class Client:
    def __init__(self, replies): self.replies=iter(replies); self.calls=[]
    def review(self, prompt): self.calls.append(prompt);return next(self.replies)

class SemanticTests(unittest.TestCase):
    def test_invalid_first_answer_gets_one_bounded_repair(self):
        client=Client([{'clips':[{'first_id':0,'last_id':1}],'reason':'wrong'}, {'clips':[],'reason':'no complete content'}])
        decision,valid,rejected=select_valid(client,[{'id':0,'start':0,'end':40,'text':'x'}],40)
        self.assertEqual(valid,[]);self.assertEqual(len(client.calls),2)
        self.assertTrue(rejected)

    def test_empty_valid_answer_does_not_retry_to_force_quota(self):
        client=Client([{'clips':[],'reason':'no product explanation'}])
        decision,valid,rejected=select_valid(client,[],360)
        self.assertEqual(len(client.calls),1);self.assertEqual(valid,[])

if __name__=='__main__':unittest.main()
