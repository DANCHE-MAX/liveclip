import tempfile, unittest
from pathlib import Path
from liveclip.daily_budget import DailyBudget

class DailyBudgetTests(unittest.TestCase):
 def test_caps_unique_reservations_at_eleven_and_reuses_without_charging(self):
  with tempfile.TemporaryDirectory() as d:
   q=DailyBudget(Path(d)/'budget.db')
   for i in range(11):self.assertEqual(q.reserve('2026-11-19',f'window{i}'),'reserved')
   self.assertEqual(q.reserve('2026-11-19','window0'),'existing')
   self.assertEqual(q.reserve('2026-11-19','window11'),'limit_reached')
   self.assertEqual(q.reserve('2026-11-20','window11'),'reserved')
