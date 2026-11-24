"""Default-paused native-channel polling extension; called by existing comment job.
Credentials stay in host environment; account identities and approval are local controls.
"""
import json,os,time
from pathlib import Path
from nv_community_runtime import connect,dispatch,DATA
from nv_community_native_adapters import InstagramAdapter,YouTubeAdapter,NativeAccessError
HERE=Path(__file__).resolve().parent
CONTROL=DATA/'nv_community_native_accounts.json'

def initialize_controls():
 DATA.mkdir(parents=True,exist_ok=True)
 if CONTROL.exists():return
 seed=HERE/'nv_community_native_accounts.json'
 if not seed.exists():return
 content=seed.read_text();json.loads(content)
 try:fd=os.open(CONTROL,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 except FileExistsError:return
 with os.fdopen(fd,'w') as f:f.write(content)

def run_native_accounts(read_only=False, preview=False):
 initialize_controls()
 if not CONTROL.exists():return {}
 config=json.loads(CONTROL.read_text());result={};db=connect()
 try:
  for row in config.get('accounts',[]):
   key=row['platform']+':'+row['handle']
   if preview and not row.get('dry_run_enabled',False):result[key]='preview_not_enabled';continue
   if row.get('paused',True) and not preview:result[key]='paused';continue
   if not row.get('native_id') or not row.get('token_env'):
    result[key]='identity_or_credentials_not_verified';continue
   token=os.environ.get(row['token_env'],'')
   if not token:result[key]='native_token_not_provisioned';continue
   cls={'instagram':InstagramAdapter,'youtube':YouTubeAdapter}.get(row['platform'])
   if not cls:result[key]='unsupported_native_transport';continue
   try:
    kw={'login':row.get('login','instagram')} if row['platform']=='instagram' else {}
    adapter=cls(token,row['native_id'],row['handle'],scopes=row.get('verified_scopes',[]),public_replies_approved=(not read_only and not preview and row.get('founder_public_replies_approved') is True),**kw)
    adapter.identity();media=adapter.list_media()
    # Read-only validation remains possible before public activation approval.
    seen=0;sent=0;previewed=0
    for item in media[:25]:
     for comment in adapter.list_comments(item):
      if comment.author == adapter.expected_id:continue
      seen+=1
      if preview:
       outcome=dispatch(db,adapter.platform+':'+adapter.expected_id,comment.id,comment.thread,comment.author,comment.text,row['brand'],lambda _:None,prior=comment.own_reply,followup=comment.followup,dry_run=True)
       if outcome != 'preview_duplicate':previewed+=1
       if previewed>=20:break
       continue
      if read_only or not row.get('founder_public_replies_approved',False):continue
      outcome=adapter.dispatch(db,comment,row['brand'])
      if outcome=='sent':sent+=1;time.sleep(2)
      if outcome=='uncertain':raise NativeAccessError('uncertain_delivery_review')
      if sent>=20 or previewed>=20:break
     if sent>=20 or previewed>=20:break
    result[key]=('preview_recorded_'+str(previewed)) if preview else 'read_verified_%d_sent_%d'%(seen,sent)
   except NativeAccessError as e:result[key]=str(e)
 finally:db.close()
 return result

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--preview',action='store_true');parser.add_argument('--check',action='store_true');args=parser.parse_args()
 print(json.dumps(run_native_accounts(read_only=args.check,preview=args.preview),indent=2))
