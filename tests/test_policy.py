import unittest
from datetime import datetime
from liveclip.policy import validate_candidate, validate_visual, rank_peaks, restore_subject

SEGMENTS = [
    {'id':0,'start':0.,'end':7.,'text':'这件毛衣用羊毛混纺，摸起来柔软不扎。'},
    {'id':1,'start':7.,'end':15.,'text':'落肩宽松版型，里面叠一件打底也不会紧。'},
    {'id':2,'start':15.,'end':22.,'text':'最后二十分钟截单，我们四点钟下班。'},
]
def candidate():
    return dict(first_id=0,last_id=1,kind='product_explanation',product='毛衣',
                facts=[{'quote':'羊毛混纺','type':'material'}, {'quote':'落肩宽松版型','type':'fit'}],
                information_score=4,completeness_score=4,filler_ratio=.05,complete=True,reason='面料和版型讲解完整')

class PolicyTests(unittest.TestCase):
    def test_product_passes(self):
        self.assertAlmostEqual(validate_candidate(candidate(),SEGMENTS,22)['end'],15)
    def test_sales_reminder_rejected_even_when_complete(self):
        c=candidate();c.update(kind='urgency',first_id=1,last_id=2)
        with self.assertRaises(ValueError):validate_candidate(c,SEGMENTS,22)
    def test_hallucinated_fact_rejected(self):
        c=candidate();c['facts'][0]['quote']='100%羊绒'
        with self.assertRaises(ValueError):validate_candidate(c,SEGMENTS,22)
    def test_missing_context_or_truncated_boundary_rejected(self):
        c=candidate();c['complete']=False
        with self.assertRaises(ValueError):validate_candidate(c,SEGMENTS,22)
    def test_uncertain_alignment_cannot_be_exported(self):
        segments=[dict(s) for s in SEGMENTS]; segments[0]['alignment_uncertain']=True
        with self.assertRaises(ValueError): validate_candidate(candidate(),segments,22)
    def test_cut_starting_with_dependent_verb_is_rejected(self):
        segments=[dict(s) for s in SEGMENTS]
        segments[0]['text']='给你们做的是羊毛混纺，摸起来柔软不扎。'
        with self.assertRaises(ValueError): validate_candidate(candidate(),segments,22)
    def test_subject_can_be_restored_from_immediately_previous_segment(self):
        rows=[{'id':9,'start':0,'end':2,'text':'这一款17号'}, {'id':10,'start':2,'end':10,'text':'给你们做的是抗静电面料'}, {'id':11,'start':10,'end':17,'text':'穿着舒适'}]
        c={'first_id':10,'last_id':11}
        self.assertEqual(restore_subject(c,rows)['first_id'],9)
    def test_does_not_restore_unrelated_previous_text(self):
        rows=[{'id':9,'start':0,'end':2,'text':'抓紧时间下单'}, {'id':10,'start':2,'end':10,'text':'给你们做的是抗静电面料'}, {'id':11,'start':10,'end':17,'text':'穿着舒适'}]
        c={'first_id':10,'last_id':11}
        self.assertEqual(restore_subject(c,rows)['first_id'],10)
    def test_empty_scene_rejected(self):
        with self.assertRaises(ValueError):validate_visual(dict(product_visible_ratio=.2,empty_ratio=.8,matches_product=True,complete=True,reason='空镜'))
    def test_unknown_visual_rejected(self):
        with self.assertRaises(ValueError):validate_visual({})
    def test_cross_midnight_and_nearby_peak_dedup(self):
        peaks=[dict(time='2026-11-19T00:01:00+08:00',sales=100),dict(time='2026-11-19T00:02:00+08:00',sales=90),dict(time='2026-11-19T01:00:00+08:00',sales=80)]
        windows=rank_peaks(peaks,3)
        self.assertEqual(len(windows),2)
        self.assertEqual((datetime.fromisoformat(windows[0]['end'])-datetime.fromisoformat(windows[0]['start'])).total_seconds(),360)
        self.assertTrue(windows[0]['start'].startswith('2026-11-18'))
    def test_missing_sales_not_zero(self):
        with self.assertRaises(ValueError):rank_peaks([dict(time='2026-11-19T00:01:00+08:00',sales=None)],3)

if __name__=='__main__':unittest.main()

class PromotionSafetyTests(unittest.TestCase):
    def test_coupon_inside_product_segment_is_rejected(self):
        rows=[dict(s) for s in SEGMENTS]
        rows[1]['text'] += ' 今天领券到手只要199元。'
        with self.assertRaises(ValueError): validate_candidate(candidate(),rows,22)

    def test_material_grams_not_misidentified_as_price(self):
        rows=[dict(s) for s in SEGMENTS]
        rows[0]['text'] += ' 面料克重是200克。'
        self.assertAlmostEqual(validate_candidate(candidate(),rows,22)['end'],15)

    def test_limited_time_sales_language_rejected(self):
        rows=[dict(s) for s in SEGMENTS]
        rows[1]['text'] += ' 今天买得最多。'
        with self.assertRaises(ValueError): validate_candidate(candidate(),rows,22)
