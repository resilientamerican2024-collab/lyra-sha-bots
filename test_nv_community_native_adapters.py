import unittest
from unittest.mock import Mock
from nv_community_native_adapters import InstagramAdapter,YouTubeAdapter,NativeAccessError

IG={'instagram_business_basic','instagram_business_manage_comments'}
YT={'https://www.googleapis.com/auth/youtube.force-ssl'}
def response(body,status=200):
 r=Mock();r.ok=status<400;r.status_code=status;r.json.return_value=body;return r
class AdapterTests(unittest.TestCase):
 def test_missing_scope_no_network(self):
  session=Mock();a=InstagramAdapter('secret','123','brand',session=session)
  with self.assertRaisesRegex(NativeAccessError,'scopes'):a.identity()
  session.request.assert_not_called()
 def test_identity_mismatch_blocks(self):
  session=Mock();session.request.return_value=response({'id':'123','username':'other'})
  a=InstagramAdapter('secret','123','brand',scopes=IG,session=session)
  with self.assertRaisesRegex(NativeAccessError,'identity_mismatch'):a.list_comments('media')
  self.assertEqual(session.request.call_count,1)
 def test_default_approval_blocks_before_network(self):
  session=Mock();a=InstagramAdapter('secret','123','brand',scopes=IG,session=session)
  with self.assertRaisesRegex(NativeAccessError,'approval_required'):a.reply('c','Hello')
  session.request.assert_not_called()
 def test_owned_media_and_existing_reply(self):
  session=Mock();session.request.side_effect=[response({'id':'123','username':'brand'}),response({'data':[{'id':'media'}]}),response({'data':[{'id':'c','text':'Hello','from':{'id':'person'}}]}),response({'data':[{'id':'old','from':{'id':'123'}}]})]
  a=InstagramAdapter('secret','123','brand',scopes=IG,session=session)
  rows=a.list_comments('media');self.assertTrue(rows[0].own_reply)
  self.assertEqual(session.request.call_args_list[-1].args[1],'https://graph.instagram.com/v22.0/c/replies')
 def test_foreign_media_blocks(self):
  session=Mock();session.request.side_effect=[response({'id':'123','username':'brand'}),response({'data':[{'id':'owned'}]})]
  a=InstagramAdapter('secret','123','brand',scopes=IG,session=session)
  with self.assertRaisesRegex(NativeAccessError,'not_owned'):a.list_comments('foreign')
 def test_reply_unseen_target_blocks(self):
  session=Mock();session.request.return_value=response({'id':'123','username':'brand'})
  a=InstagramAdapter('secret','123','brand',scopes=IG,session=session,public_replies_approved=True)
  with self.assertRaisesRegex(NativeAccessError,'not_read'):a.reply('foreign','Hello')
  self.assertTrue(all(c.args[0]=='GET' for c in session.request.call_args_list))
 def test_youtube_read_ownership_and_payload(self):
  session=Mock();session.request.side_effect=[response({'items':[{'id':'channel','snippet':{'customUrl':'@brand'}}]}),response({'items':[{'id':'vid','snippet':{'channelId':'channel'}}]}),response({'items':[{'snippet':{'topLevelComment':{'id':'c','snippet':{'authorChannelId':{'value':'person'},'textOriginal':'Hello'}}}}]}),response({'id':'reply'})]
  a=YouTubeAdapter('secret','channel','brand',scopes=YT,session=session,public_replies_approved=True)
  self.assertEqual(a.list_comments('vid')[0].id,'c');self.assertEqual(a.reply('c','Hi')['id'],'reply')
  call=session.request.call_args
  self.assertEqual(call.kwargs['json'],{'snippet':{'parentId':'c','textOriginal':'Hi'}})
  self.assertEqual(call.args[:2],('POST','https://www.googleapis.com/youtube/v3/comments'))
 def test_youtube_uploads_pagination(self):
  session=Mock();session.request.side_effect=[response({'items':[{'id':'channel','snippet':{'customUrl':'@brand'}}]}),response({'items':[{'id':'channel','contentDetails':{'relatedPlaylists':{'uploads':'uploads'}}}]}),response({'items':[{'contentDetails':{'videoId':'v1'}}],'nextPageToken':'next'}),response({'items':[{'contentDetails':{'videoId':'v2'}}]})]
  a=YouTubeAdapter('secret','channel','brand',scopes=YT,session=session)
  self.assertEqual(a.list_media(),['v1','v2'])
  self.assertEqual(session.request.call_args.kwargs['params']['pageToken'],'next')
 def test_youtube_uploads_wrong_channel_blocks(self):
  session=Mock();session.request.side_effect=[response({'items':[{'id':'channel','snippet':{'customUrl':'@brand'}}]}),response({'items':[{'id':'other','contentDetails':{'relatedPlaylists':{'uploads':'foreign'}}}]})]
  a=YouTubeAdapter('secret','channel','brand',scopes=YT,session=session)
  with self.assertRaisesRegex(NativeAccessError,'identity_mismatch'):a.list_media()
  self.assertEqual(session.request.call_count,2)
 def test_error_sanitized(self):
  session=Mock();session.request.side_effect=RuntimeError('TOKEN_SECRET')
  a=YouTubeAdapter('TOKEN_SECRET','channel','brand',scopes=YT,session=session)
  with self.assertRaises(NativeAccessError) as ctx:a.identity()
  self.assertNotIn('TOKEN_SECRET',str(ctx.exception))
 def test_youtube_force_ssl_required_for_reply(self):
  session=Mock();session.request.return_value=response({'items':[{'id':'channel','snippet':{'customUrl':'@brand'}}]})
  a=YouTubeAdapter('secret','channel','brand',scopes={'https://www.googleapis.com/auth/youtube.readonly'},session=session,public_replies_approved=True)
  a.identity();a._read_comments.add('c')
  with self.assertRaisesRegex(NativeAccessError,'scopes'):a.reply('c','Hi')
  self.assertEqual(session.request.call_count,1)
if __name__=='__main__':unittest.main()
