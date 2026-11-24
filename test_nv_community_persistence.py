import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
import nv_community_runtime as r
class PersistenceTests(unittest.TestCase):
 def test_bootstrap_preserves_existing_pause_file(self):
  with tempfile.TemporaryDirectory() as d:
   data=Path(d)/'volume';control=data/'nv_community_accounts.json'
   with patch.object(r,'DATA',data),patch.object(r,'CONTROL',control):
    r.initialize_persistent_controls();initial=json.loads(control.read_text());self.assertTrue(all(x['paused'] for x in initial['accounts'].values()))
    control.write_text('{"operator":"preserved"}');r.initialize_persistent_controls();self.assertEqual(json.loads(control.read_text()),{'operator':'preserved'})
 def test_database_reopen_preserves_dedupe(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'events.sqlite3';db=r.connect(path)
   db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',('a','c','t','u','review','sensitive','','now'));db.commit();db.close()
   reopened=r.connect(path);self.assertEqual(reopened.execute('SELECT status FROM events').fetchone()[0],'review');reopened.close()
if __name__=='__main__':unittest.main()
