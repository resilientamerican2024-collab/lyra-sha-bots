import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
import nv_community_native_runtime as r
class NativeRuntimeTests(unittest.TestCase):
 def test_default_paused_never_creates_adapter(self):
  with tempfile.TemporaryDirectory() as d:
   control=Path(d)/'controls.json';control.write_text(json.dumps({'accounts':[{'platform':'instagram','handle':'example','paused':True}]}))
   with patch.object(r,'CONTROL',control),patch.object(r,'initialize_controls'),patch.object(r,'connect') as db,patch.object(r,'InstagramAdapter') as adapter:
    self.assertEqual(r.run_native_accounts(),{'instagram:example':'paused'});adapter.assert_not_called()
 def test_missing_native_identity_never_connects(self):
  with tempfile.TemporaryDirectory() as d:
   control=Path(d)/'controls.json';control.write_text(json.dumps({'accounts':[{'platform':'youtube','handle':'example','paused':False}]}))
   with patch.object(r,'CONTROL',control),patch.object(r,'initialize_controls'),patch.object(r,'connect'),patch.object(r,'YouTubeAdapter') as adapter:
    self.assertEqual(r.run_native_accounts(),{'youtube:example':'identity_or_credentials_not_verified'});adapter.assert_not_called()
 def test_read_only_overrides_any_local_public_activation_flag(self):
  from unittest.mock import Mock
  from nv_community_native_adapters import IncomingComment
  with tempfile.TemporaryDirectory() as d:
   control=Path(d)/'controls.json';control.write_text(json.dumps({'accounts':[{'platform':'instagram','handle':'brand','paused':False,'native_id':'id','token_env':'TEST_TOKEN','brand':'trending_edit','founder_public_replies_approved':True}]}))
   with patch.object(r,'CONTROL',control),patch.object(r,'initialize_controls'),patch.object(r,'connect'),patch.dict(r.os.environ,{'TEST_TOKEN':'TEST'}),patch.object(r,'InstagramAdapter') as cls:
    a=cls.return_value;a.expected_id='id';a.list_media.return_value=['media'];a.list_comments.return_value=[IncomingComment('c','c','person','Hello')]
    result=r.run_native_accounts(read_only=True)
    self.assertFalse(cls.call_args.kwargs['public_replies_approved']);a.dispatch.assert_not_called();self.assertIn('sent_0',result['instagram:brand'])
if __name__=='__main__':unittest.main()
