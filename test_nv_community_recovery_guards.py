import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
import nv_community_runtime as r
class RecoveryGuardTests(unittest.TestCase):
 def test_facebook_wrong_token_principal_stops_before_comments(self):
  with tempfile.TemporaryDirectory() as d:
   controls=Path(d)/'controls.json';controls.write_text(json.dumps({'accounts':{'expected':{'brand':'trending_edit','paused':False,'verified_names':['Page']}}}))
   db=r.connect(Path(d)/'db')
   with patch.object(r,'CONTROL',controls),patch.object(r,'initialize_persistent_controls'),patch.object(r,'connect',return_value=db),patch.object(r,'graph',return_value={'id':'different','name':'Page'}) as graph:
    _,result=r.run_accounts({'facebook_clients':[{'page_id':'expected','page_access_token':'TEST'}]})
   self.assertEqual(result['expected'],'token_principal_mismatch');self.assertEqual(graph.call_count,1);self.assertEqual(graph.call_args.args[1],'me')
 def test_instagram_checks_token_principal_not_requested_object(self):
  from unittest.mock import Mock
  from nv_community_native_adapters import InstagramAdapter
  session=Mock();response=Mock();response.ok=True;response.json.return_value={'id':'expected','username':'handle'};session.request.return_value=response
  adapter=InstagramAdapter('TEST','expected','handle',scopes={'instagram_business_basic','instagram_business_manage_comments'},session=session)
  adapter.identity();self.assertEqual(session.request.call_args.args[1],'https://graph.instagram.com/v22.0/me')
 def test_instagram_facebook_login_checks_linked_account(self):
  from unittest.mock import Mock
  from nv_community_native_adapters import InstagramAdapter,NativeAccessError
  session=Mock();response=Mock();response.ok=True;response.json.return_value={'id':'page','instagram_business_account':{'id':'wrong','username':'handle'}};session.request.return_value=response
  adapter=InstagramAdapter('TEST','expected','handle',login='facebook',scopes={'instagram_basic','instagram_manage_comments','pages_read_engagement'},session=session)
  with self.assertRaises(NativeAccessError):adapter.identity()
if __name__=='__main__':unittest.main()
