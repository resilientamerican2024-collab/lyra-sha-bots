import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import nv_community_runtime as r

class RuntimeTests(unittest.TestCase):
 def test_verified_landmarks(self):
  from nv_community_engine import respond
  for place in ('Orchard Beach','Yankee Stadium','Pelham Bay Park','Fordham Rd'):
   result=respond('Hello from '+place)
   self.assertEqual(result['action'],'reply');self.assertTrue(set(result['communities']).intersection({'Bronx','Fordham'}))
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); self.db=r.connect(Path(self.temp.name)/'db')
 def tearDown(self): self.db.close();self.temp.cleanup()
 def event(self, comment='1',send=None,**kw):
  return r.dispatch(self.db,'page',comment,'thread','person','hello','trending_edit',send or (lambda text:{'id':'receipt'}),**kw)
 @patch.object(r,'respond',return_value={'action':'reply','text':'Welcome!','reason':'greeting'})
 def test_dedupe_and_followup(self,_):
  self.assertEqual(self.event(),'sent');self.assertEqual(self.event(),'duplicate')
  self.assertEqual(self.event('2'),'sent');self.assertEqual(self.event('3'),'ignore')
 @patch.object(r,'respond',return_value={'action':'reply','text':'Welcome!'})
 def test_uncertain_not_retried(self,_):
  def fail(text): raise TimeoutError()
  self.assertEqual(self.event(send=fail),'uncertain'); self.assertEqual(self.event(),'duplicate')
 @patch.object(r,'respond',return_value={'action':'reply','text':'Welcome!'})
 def test_one_followup_to_preexisting_reply(self,_):
  self.assertEqual(self.event(prior=True),'ignore')
  self.assertEqual(self.event('2',followup=True),'sent')
  self.assertEqual(self.event('3',followup=True),'ignore')
 @patch.object(r,'respond',return_value={'action':'review','reason':'sensitive'})
 def test_review_never_sends(self,_):
  self.assertEqual(self.event(send=lambda _:self.fail('sent review')),'review')
  self.assertEqual(self.event('2',prior=True,send=lambda _:self.fail('sent review')),'review')
  self.db.execute("UPDATE events SET status='sent'");self.db.commit()
  self.assertEqual(self.event('3',send=lambda _:self.fail('sent review')),'review')
 @patch.object(r,'respond',return_value={'action':'reply','text':'Hello'})
 def test_existing_reply_never_sends(self,_):
  self.assertEqual(self.event(prior=True,send=lambda _:self.fail('duplicate')),'ignore')
 @patch.object(r,'graph')
 def test_paused_no_network(self,graph):
  with patch.object(r,'DB',Path(self.temp.name)/'other'),patch.object(r,'connect',return_value=self.db):
   owned, result=r.run_accounts({'facebook_clients':[{'page_id':'813874968486490','page_access_token':'TEST'}]})
  graph.assert_not_called();self.assertEqual(result['813874968486490'],'paused')
  self.db=r.connect(Path(self.temp.name)/'db')
if __name__=='__main__':unittest.main()
