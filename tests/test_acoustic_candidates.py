import unittest
from liveclip.acoustic_candidates import propose

class AcousticTests(unittest.TestCase):
    def test_only_breath_boundaries_and_no_used_intervals(self):
        gaps=[(0,.3),(7,7.3),(16,16.8),(25,25.4),(35,35.6),(48,48.5)]
        result=propose(gaps,60,[(15,18)])
        self.assertTrue(result)
        for start,end in result:
            self.assertTrue(10<=end-start<=30)
            self.assertFalse(start<18 and end>15)
            self.assertTrue(any(a<=start<=b for a,b in gaps))
            self.assertTrue(any(a<=end<=b for a,b in gaps))

    def test_no_safe_breaths_yields_no_forced_clips(self):
        self.assertEqual(propose([],360,[]),[])

if __name__=='__main__':unittest.main()
