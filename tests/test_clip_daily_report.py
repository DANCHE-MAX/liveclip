import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
from liveclip import clip_daily_report as report


class DailyReportTests(unittest.TestCase):
    def test_top_queries_only_that_accounts_yesterday_new_clips(self):
        class API:
            def __init__(self):self.requests=[]
            def fetch(self,account,day,ids):self.requests.append((account,ids));return [],[]
        api=API();rows=[dict(account=report.ACCOUNTS[0][0],sha256='old',material_id='10',name='old',first_confirmed='2026-11-18'),
                        dict(account=report.ACCOUNTS[0][0],sha256='new',material_id='11',name='new',first_confirmed='2026-11-19')]
        with tempfile.TemporaryDirectory() as folder, patch.object(report,'registry',return_value=rows):
            result=report.collect('2026-11-19',Path(folder),api)
        self.assertEqual(api.requests,[(report.ACCOUNTS[0][0],['11'])])
        self.assertEqual(result['new_count'],1)
        self.assertEqual(result['accounts'][1]['registered_material_count'],0)
    def test_duplicate_account_configuration_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'config').mkdir()
            (root/'config/clip_daily_accounts.json').write_text(json.dumps([{'id':'1','name':'A'},{'id':'1','name':'B'}]))
            with self.assertRaises(ValueError):report.accounts(root)
    def test_unique_new_counts_first_success_across_accounts(self):
        rows = [dict(sha256='a', account='1', first_confirmed='2026-11-19'),
                dict(sha256='a', account='2', first_confirmed='2026-11-20'),
                dict(sha256='b', account='1', first_confirmed='2026-11-20')]
        self.assertEqual(report.new_count(rows, '2026-11-20'), 1)

    def test_missing_date_does_not_claim_complete_count(self):
        self.assertIsNone(report.new_count([dict(sha256='a', account='1', first_confirmed=None)], '2026-11-20'))

    def test_rank_excludes_zero_missing_and_nonconverting(self):
        rows = [dict(material_id='a', spend=20, gmv=100, orders=1),
                dict(material_id='b', spend=10, gmv=100, orders=2),
                dict(material_id='c', spend=None, gmv=100, orders=2),
                dict(material_id='d', spend=0, gmv=200, orders=1),
                dict(material_id='e', spend=20, gmv=0, orders=0)]
        self.assertEqual([r['material_id'] for r in report.rank(rows)], ['b', 'a'])

    def test_incomplete_account_never_presents_top(self):
        text = report.render({'date':'2026-11-19','new_count':3,'accounts':[
            {'name':'账号一','complete':False,'error':'api_40100','top':[dict(name='错误榜单',spend=1,gmv=100,orders=1,roi=100)]}]})
        self.assertNotIn('错误榜单', text)
        self.assertIn('待核验',text)

if __name__ == '__main__': unittest.main()
