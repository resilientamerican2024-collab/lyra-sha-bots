"""Private previews must never publish or mutate live dedupe/rotation."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import nv_community_runtime as fb
import nv_community_native_runtime as native
from nv_community_native_adapters import IncomingComment

class DryRunTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'db';self.db=fb.connect(self.path)
 def tearDown(self):self.db.close();self.temp.cleanup()
 def preview(self,cid='c',text='Hola soy de Ponce y Bronx',author='person',**kw):
  return fb.dispatch(self.db,'page',cid,'c',author,text,'trending_edit',lambda _:self.fail('preview published'),dry_run=True,**kw)
 def test_preview_generates_actual_policy_copy_privately(self):
  self.assertEqual(self.preview(),'would_reply')
  row=self.db.execute('SELECT status,reply,input_sha256 FROM dry_runs').fetchone()
  self.assertIn('Ponce',row[1]);self.assertIn('Bronx',row[1]);self.assertEqual(len(row[2]),64)
  self.assertEqual(self.db.execute('SELECT count(*) FROM events').fetchone()[0],0)
  self.assertEqual(self.db.execute('SELECT count(*) FROM rotations').fetchone()[0],0)
  self.assertEqual(self.path.stat().st_mode&0o777,0o600)
 def test_preview_dedupe_independent_from_live_sends(self):
  self.assertEqual(self.preview(),'would_reply');self.assertEqual(self.preview(),'preview_duplicate')
  send=Mock(return_value={'id':'reply'})
  self.assertEqual(fb.dispatch(self.db,'page','c','c','person','Hola soy de Ponce y Bronx','trending_edit',send),'sent');send.assert_called_once()
 def test_sensitive_and_unknown_author_stay_review(self):
  self.assertEqual(self.preview(text='Hello I cannot breathe'),'review')
  self.assertEqual(self.preview('unknown',text='Hello',author=''),'review')
  self.assertEqual(self.db.execute("SELECT count(*) FROM dry_runs WHERE status='review' AND reply='' ").fetchone()[0],2)
 def test_prior_reply_preview_not_scheduled(self):
  self.assertEqual(self.preview(prior=True),'ignore')
  self.assertEqual(self.db.execute('SELECT reason FROM dry_runs').fetchone()[0],'page_already_replied')
 def test_preview_followup_limit_without_live_rotation_mutation(self):
  self.assertEqual(self.preview(),'would_reply')
  self.assertEqual(self.preview('followup',text='Gracias',followup=True),'would_reply')
  self.assertEqual(self.preview('secondfollowup',text='Gracias',followup=True),'ignore')
  self.assertEqual(self.db.execute('SELECT count(*) FROM rotations').fetchone()[0],0)
 def test_facebook_preview_optin_does_not_unpause_public_control(self):
  control=Path(self.temp.name)/'fbcontrols';control.write_text(json.dumps({'accounts':{'page':{'paused':True,'dry_run_enabled':True,'brand':'trending_edit','verified_names':['Brand']}}}))
  def graph(method,path,token,**kwargs):
   self.assertEqual(method,'GET');self.assertEqual(path,'me');return {'id':'page','name':'Brand'}
  def pages(path,token,**kwargs):
   return iter([{'id':'post'}] if path=='page/posts' else [{'id':'c','from':{'id':'person'},'message':'Hello from Bronx'}] if path=='post/comments' else [])
  with patch.object(fb,'CONTROL',control),patch.object(fb,'initialize_persistent_controls'),patch.object(fb,'connect',return_value=self.db),patch.object(fb,'graph',side_effect=graph),patch.object(fb,'pages',side_effect=pages):
   _,result=fb.run_accounts({'facebook_clients':[{'page_id':'page','page_access_token':'TEST'}]},preview=True)
  self.assertEqual(result['page'],'preview_recorded_1');self.assertTrue(json.loads(control.read_text())['accounts']['page']['paused'])
  self.db=fb.connect(self.path)
  self.assertEqual(self.db.execute('SELECT count(*) FROM dry_runs').fetchone()[0],1)
 def test_preview_without_explicit_optin_never_uses_network(self):
  control=Path(self.temp.name)/'fbcontrols';control.write_text(json.dumps({'accounts':{'page':{'paused':True,'brand':'trending_edit'}}}))
  with patch.object(fb,'CONTROL',control),patch.object(fb,'initialize_persistent_controls'),patch.object(fb,'connect',return_value=self.db),patch.object(fb,'graph') as graph:
   _,result=fb.run_accounts({'facebook_clients':[{'page_id':'page','page_access_token':'TEST'}]},preview=True)
  graph.assert_not_called();self.assertEqual(result['page'],'preview_not_enabled');self.db=fb.connect(self.path)
 def test_native_preview_bypasses_public_pause_for_gets_only(self):
  control=Path(self.temp.name)/'nativecontrols';control.write_text(json.dumps({'accounts':[{'platform':'instagram','handle':'brand','native_id':'ig-id','token_env':'TEST_TOKEN','paused':True,'dry_run_enabled':True,'founder_public_replies_approved':False,'brand':'trending_edit'}]}))
  with patch.object(native,'CONTROL',control),patch.object(native,'initialize_controls'),patch.object(native,'connect',return_value=self.db),patch.dict(native.os.environ,{'TEST_TOKEN':'TEST'}),patch.object(native,'InstagramAdapter') as cls:
   adapter=cls.return_value;adapter.expected_id='ig-id';adapter.platform='instagram';adapter.list_media.return_value=['media'];adapter.list_comments.return_value=[IncomingComment('c','c','person','Hello from Bronx')]
   result=native.run_native_accounts(preview=True)
   self.assertFalse(cls.call_args.kwargs['public_replies_approved']);adapter.dispatch.assert_not_called();adapter.reply.assert_not_called()
  self.assertEqual(result['instagram:brand'],'preview_recorded_1');self.db=fb.connect(self.path)
  self.assertEqual(self.db.execute('SELECT status FROM dry_runs').fetchone()[0],'would_reply')

if __name__=='__main__':unittest.main()
