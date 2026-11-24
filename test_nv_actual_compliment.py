import unittest,tempfile
from pathlib import Path
import nv_community_runtime as r
class ActualComplimentTests(unittest.TestCase):
 def test_observed_nice_uses_existing_reaction_privately(self):
  with tempfile.TemporaryDirectory() as d:
   db=r.connect(Path(d)/'db')
   status=r.dispatch(db,'account','comment','thread','author','Nice','trending_edit',lambda _:self.fail('public send'),dry_run=True)
   self.assertEqual(status,'would_reply');row=db.execute('SELECT reply FROM dry_runs').fetchone();self.assertTrue(row[0]);self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],0);db.close()
 def test_nice_cannot_hide_extra_prose(self):
  with tempfile.TemporaryDirectory() as d:
   db=r.connect(Path(d)/'db')
   status=r.dispatch(db,'account','comment','thread','author','Nice I want to die','trending_edit',lambda _:self.fail('public send'),dry_run=True)
   self.assertEqual(status,'review');db.close()
if __name__=='__main__':unittest.main()
