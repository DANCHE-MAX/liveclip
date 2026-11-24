import unittest


class CandidateTimingTests(unittest.TestCase):
    def test_model_times_cannot_force_cut_outside_quiet_gaps(self):
        from liveclip.doubao_clips import safe_bounds
        self.assertEqual(safe_bounds(1,19,[(.8,1.1),(18.8,19.5)],60),(1.06,19.3))
        with self.assertRaises(ValueError): safe_bounds(1,19,[],60)
        with self.assertRaises(ValueError): safe_bounds(1,31,[(.8,1.1),(30.9,31.6)],60)

    def test_audio_boundary_and_conjunction_fail_closed(self):
        from liveclip.doubao_clips import require_boundary
        with self.assertRaises(ValueError): require_boundary({'accept':True,'boundary_complete':True,'boundary_reason':'looks done','transcript':'白色更清爽而且'})
        with self.assertRaises(ValueError): require_boundary({'accept':True,'boundary_complete':None,'transcript':'完整。'})

    def test_acoustic_locator_uses_observed_windows_and_cannot_prove_semantics(self):
        from liveclip.doubao_clips import acoustic_locator
        gaps=[(0,.3),(8,8.3),(18,18.8),(27,27.4),(38,38.6),(49,49.5)]
        start,end=acoustic_locator(10,17,gaps,60)
        self.assertTrue(10<=end-start<=30)
        self.assertTrue(any(a<=start<=b for a,b in gaps))
        self.assertTrue(any(a<=end<=b for a,b in gaps))
        with self.assertRaises(ValueError): acoustic_locator(10,17,[],60)


if __name__=='__main__': unittest.main()
