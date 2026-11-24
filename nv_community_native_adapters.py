"""Native transport extensions for the EXISTING community engine; not an application.
No OAuth/grant changes, refresh, startup scheduling, or writes at import time.
Public replies default OFF; activation must be supplied by trusted host configuration
only after Founder approval. Incoming comment data never controls this setting.
Sources: Meta Comment Moderation; YouTube Data API comments.insert/commentThreads.list.
"""
from dataclasses import dataclass
from urllib.parse import quote
import requests

class NativeAccessError(Exception):
    """Sanitized exception; provider bodies/credential-bearing URLs are not logged."""

@dataclass(frozen=True)
class IncomingComment:
    id: str
    thread: str
    author: str
    text: str
    own_reply: bool = False
    followup: bool = False

class NativeAdapter:
    platform = ''
    def __init__(self, token, expected_id, expected_handle, scopes=(), session=None,
                 public_replies_approved=False):
        if not token or not expected_id or not expected_handle:
            raise NativeAccessError('credentials_and_expected_identity_required')
        self._token=token
        self.expected_id=str(expected_id)
        self.expected_handle=expected_handle.lstrip('@')
        self.scopes=set(scopes)
        self.session=session or requests.Session()
        self._approved = public_replies_approved is True
        self._identity_verified=False
        self._read_comments=set()

    def _request(self, method, url, **kwargs):
        if method!='GET' and not self._approved:
            raise NativeAccessError('founder_public_reply_approval_required')
        try:
            r=self.session.request(method,url,headers={'Authorization':'Bearer '+self._token},timeout=20,**kwargs)
            body=r.json()
        except Exception:
            raise NativeAccessError('native_transport_or_payload_error') from None
        if not r.ok or 'error' in body:
            raise NativeAccessError('native_http_'+str(r.status_code))
        return body

    def _scope(self, required):
        if not set(required).issubset(self.scopes):
            raise NativeAccessError('required_native_scopes_not_verified')

    def _ensure_identity(self):
        if not self._identity_verified: self.identity()

    def _check_reply(self, comment_id):
        if not self._approved:
            raise NativeAccessError('founder_public_reply_approval_required')
        self._ensure_identity()
        if str(comment_id) not in self._read_comments:
            raise NativeAccessError('reply_target_not_read_from_owned_media')

    def _check_identity(self, account_id, handle):
        if str(account_id)!=self.expected_id or handle.lstrip('@').casefold()!=self.expected_handle.casefold():
            self._identity_verified=False
            raise NativeAccessError('native_identity_mismatch')
        self._identity_verified=True

    def dispatch(self, db, comment, brand, catalog=None):
        """Reuse existing policy, durable dedupe, review queue and one-followup limit."""
        from nv_community_runtime import dispatch
        if not self._approved:
            raise NativeAccessError('founder_public_reply_approval_required')
        self._ensure_identity()
        account=self.platform+':'+self.expected_id
        return dispatch(db,account,comment.id,comment.thread,comment.author,comment.text,
                        brand,lambda text:self.reply(comment.id,text),prior=comment.own_reply,
                        followup=comment.followup,catalog=catalog)

class InstagramAdapter(NativeAdapter):
    platform='instagram'
    def __init__(self,*args,login='instagram',version='v22.0',**kwargs):
        super().__init__(*args,**kwargs)
        if login not in ('instagram','facebook'): raise NativeAccessError('unsupported_login_type')
        self.login=login
        self.base=('https://graph.instagram.com/' if login=='instagram' else 'https://graph.facebook.com/')+version
        self.required=({'instagram_business_basic','instagram_business_manage_comments'} if login=='instagram' else {'instagram_basic','instagram_manage_comments','pages_read_engagement'})
        self._owned_media=set()

    def identity(self):
        self._scope(self.required)
        if self.login == 'instagram':
            body=self._request('GET',self.base+'/me',params={'fields':'id,username'})
        else:
            principal=self._request('GET',self.base+'/me',params={'fields':'id,instagram_business_account{id,username}'})
            body=principal.get('instagram_business_account',{})
        self._check_identity(body.get('id',''),body.get('username',''))
        return {'id':body['id'],'handle':body['username'],'platform':self.platform}

    def list_media(self):
        self._ensure_identity()
        params={'fields':'id','limit':50}
        result=[]
        for _ in range(20):
            body=self._request('GET',self.base+'/'+quote(self.expected_id,safe='')+'/media',params=params)
            result.extend(str(v['id']) for v in body.get('data',[]))
            after=body.get('paging',{}).get('cursors',{}).get('after')
            if not body.get('paging',{}).get('next'): break
            if not after: raise NativeAccessError('pagination_cursor_missing')
            params['after']=after
        else: raise NativeAccessError('pagination_limit_review')
        self._owned_media.update(result)
        return result

    def list_comments(self,media_id):
        self._ensure_identity()
        if str(media_id) not in self._owned_media: self.list_media()
        if str(media_id) not in self._owned_media: raise NativeAccessError('media_not_owned_by_account')
        comments=[]
        params={'fields':'id,text,from,parent_id','limit':50}
        for _ in range(20):
            body=self._request('GET',self.base+'/'+quote(str(media_id),safe='')+'/comments',params=params)
            for row in body.get('data',[]):
                cid=str(row['id']); author=str(row.get('from',{}).get('id',''))
                # IG replies flatten to top-level; only top-level new engagement here.
                if row.get('parent_id') or author==self.expected_id: continue
                self._read_comments.add(cid)
                replies=[]
                rp={'fields':'id,from','limit':50}
                for _ in range(20):
                    rb=self._request('GET',self.base+'/'+quote(cid,safe='')+'/replies',params=rp)
                    replies.extend(rb.get('data',[]))
                    after=rb.get('paging',{}).get('cursors',{}).get('after')
                    if not rb.get('paging',{}).get('next'): break
                    if not after: raise NativeAccessError('pagination_cursor_missing')
                    rp['after']=after
                else: raise NativeAccessError('pagination_limit_review')
                own=any(str(v.get('from',{}).get('id',''))==self.expected_id for v in replies)
                comments.append(IncomingComment(cid,cid,author,row.get('text',''),own_reply=own))
            after=body.get('paging',{}).get('cursors',{}).get('after')
            if not body.get('paging',{}).get('next'): break
            if not after: raise NativeAccessError('pagination_cursor_missing')
            params['after']=after
        else: raise NativeAccessError('pagination_limit_review')
        return comments

    def reply(self,comment_id,text):
        self._check_reply(comment_id)
        if not text.strip(): raise NativeAccessError('empty_reply')
        return self._request('POST',self.base+'/'+quote(str(comment_id),safe='')+'/replies',data={'message':text})

class YouTubeAdapter(NativeAdapter):
    platform='youtube'
    base='https://www.googleapis.com/youtube/v3'
    read_scopes={'https://www.googleapis.com/auth/youtube.readonly','https://www.googleapis.com/auth/youtube.force-ssl','https://www.googleapis.com/auth/youtube'}
    def identity(self):
        if not self.scopes.intersection(self.read_scopes):
            raise NativeAccessError('required_native_scopes_not_verified')
        body=self._request('GET',self.base+'/channels',params={'part':'snippet','mine':'true'})
        for row in body.get('items',[]):
            if str(row.get('id'))==self.expected_id:
                handle=row.get('snippet',{}).get('customUrl','')
                self._check_identity(row['id'],handle)
                return {'id':row['id'],'handle':handle,'platform':self.platform}
        raise NativeAccessError('native_identity_mismatch')

    def list_media(self):
        self._ensure_identity()
        body=self._request('GET',self.base+'/channels',params={'part':'contentDetails','mine':'true'})
        owned=[v for v in body.get('items',[]) if str(v.get('id',''))==self.expected_id]
        if len(owned)!=1: raise NativeAccessError('native_identity_mismatch')
        playlist=owned[0].get('contentDetails',{}).get('relatedPlaylists',{}).get('uploads')
        if not playlist: raise NativeAccessError('uploads_playlist_unavailable')
        params={'part':'contentDetails','playlistId':playlist,'maxResults':50}
        result=[]
        for _ in range(20):
            data=self._request('GET',self.base+'/playlistItems',params=params)
            result.extend(str(v['contentDetails']['videoId']) for v in data.get('items',[]) if v.get('contentDetails',{}).get('videoId'))
            if not data.get('nextPageToken'): break
            params['pageToken']=data['nextPageToken']
        else: raise NativeAccessError('pagination_limit_review')
        return list(dict.fromkeys(result))

    def list_comments(self,video_id):
        self._ensure_identity()
        video=self._request('GET',self.base+'/videos',params={'part':'snippet','id':video_id})
        if not any(str(v.get('snippet',{}).get('channelId'))==self.expected_id for v in video.get('items',[])):
            raise NativeAccessError('media_not_owned_by_account')
        params={'part':'snippet','videoId':video_id,'maxResults':100,'textFormat':'plainText'}
        result=[]
        for _ in range(20):
            body=self._request('GET',self.base+'/commentThreads',params=params)
            for thread in body.get('items',[]):
                top=thread['snippet']['topLevelComment'];sn=top['snippet'];cid=str(top['id'])
                if str(sn.get('authorChannelId',{}).get('value',''))==self.expected_id: continue
                self._read_comments.add(cid)
                result.append(IncomingComment(cid,cid,str(sn.get('authorChannelId',{}).get('value','')),sn.get('textOriginal',sn.get('textDisplay',''))))
                # All replies are fetched to avoid partial reply arrays causing duplicates.
                if thread['snippet'].get('totalReplyCount',0):
                    reply_params={'part':'snippet','parentId':cid,'maxResults':100,'textFormat':'plainText'}
                    replies=[]
                    for _ in range(20):
                        rb=self._request('GET',self.base+'/comments',params=reply_params)
                        replies.extend(rb.get('items',[]))
                        if not rb.get('nextPageToken'): break
                        reply_params['pageToken']=rb['nextPageToken']
                    else: raise NativeAccessError('pagination_limit_review')
                    own=any(str(v.get('snippet',{}).get('authorChannelId',{}).get('value',''))==self.expected_id for v in replies)
                    if own: result[-1]=IncomingComment(cid,cid,result[-1].author,result[-1].text,own_reply=True)
                    # Follow-up transport stays disabled until threading behavior is verified live.
            if not body.get('nextPageToken'): break
            params['pageToken']=body['nextPageToken']
        else: raise NativeAccessError('pagination_limit_review')
        return result

    def reply(self,comment_id,text):
        self._check_reply(comment_id)
        self._scope({'https://www.googleapis.com/auth/youtube.force-ssl'})
        if not text.strip(): raise NativeAccessError('empty_reply')
        return self._request('POST',self.base+'/comments',params={'part':'snippet'},json={'snippet':{'parentId':str(comment_id),'textOriginal':text}})

UNCONNECTED_PLATFORMS={
 'tiktok':'TikTok Business owned-video APIs exist; Business Comment app access, creator authorization and business_id not verified. No generic Display API comment endpoint is assumed.',
 'pinterest':'Published official Pinterest OpenAPI v5.32.0 has 226 paths and no comment read/reply route. No native comment automation implemented.',
 'x':'Native replies supported, but user-context token, scopes and zero-additional-cost entitlement not verified. No requests made under $0 budget.',
 'linkedin':'Personal account comment reading requires restricted member-social feed access; approved app product/grants not verified. No substitute scraping or new app.'}
