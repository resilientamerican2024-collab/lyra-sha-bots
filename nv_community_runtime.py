"""Zero-token community lane inside the existing Facebook comment job."""
import json, sqlite3, time, re, os, hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
import requests
from nv_community_engine import respond

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', str(HERE)))
CONTROL = DATA / 'nv_community_accounts.json'
DB = DATA / 'nv_community_activity.sqlite3'

def initialize_persistent_controls():
    DATA.mkdir(parents=True, exist_ok=True)
    if DATA.resolve() == HERE.resolve(): return
    # Copy initial pauses only once; redeploy must never overwrite operator switches.
    seed = (HERE / 'nv_community_accounts.json').read_text()
    json.loads(seed)  # validate before creating a durable destination
    try:
        fd = os.open(CONTROL, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    with os.fdopen(fd, 'w') as stream:
        stream.write(seed)
BASE = 'https://graph.facebook.com/v22.0'

class GraphError(Exception):
    pass

def graph(method, path, token, **data):
    r = requests.request(method, BASE + '/' + path, headers={'Authorization': 'Bearer ' + token}, params=data if method == 'GET' else None, data=data if method == 'POST' else None, timeout=20)
    payload = r.json()
    if not r.ok or 'error' in payload:
        raise GraphError('Graph error code=' + str(payload.get('error', {}).get('code', r.status_code)))
    return payload

def pages(path, token, **params):
    # Follow cursor, never credential-bearing next URLs.
    for _ in range(20):
        data = graph('GET', path, token, **params)
        yield from data.get('data', [])
        cursor = data.get('paging', {}).get('cursors', {}).get('after')
        if not data.get('paging', {}).get('next') or not cursor:
            return
        params['after'] = cursor
    raise GraphError('pagination_limit_review')

def connect(path=DB):
    db = sqlite3.connect(path, timeout=30)
    if str(path) != ':memory:': os.chmod(path, 0o600)
    db.executescript('''CREATE TABLE IF NOT EXISTS events (account TEXT, comment TEXT, thread TEXT, author TEXT, status TEXT, reason TEXT, reply TEXT, at TEXT, PRIMARY KEY(account,comment)); CREATE TABLE IF NOT EXISTS rotations (account TEXT PRIMARY KEY, value INTEGER); CREATE TABLE IF NOT EXISTS health (account TEXT PRIMARY KEY, status TEXT, checked_at TEXT); CREATE TABLE IF NOT EXISTS dry_runs (account TEXT, comment TEXT, thread TEXT, author TEXT, status TEXT, reason TEXT, reply TEXT, input_sha256 TEXT, at TEXT, PRIMARY KEY(account,comment));''')
    return db

def dispatch(db, account, comment, thread, author, text, brand, send, prior=False, catalog=None, followup=False, dry_run=False):
    # Immediate transaction serializes all workers. Persist intent BEFORE network;
    # uncertain writes are never retried automatically.
    db.execute('BEGIN IMMEDIATE')
    if dry_run and db.execute('SELECT 1 FROM dry_runs WHERE account=? AND comment=?', (account,comment)).fetchone():
        db.rollback(); return 'preview_duplicate'
    already_handled = db.execute('SELECT 1 FROM events WHERE account=? AND comment=?', (account,comment)).fetchone()
    if already_handled and not dry_run:
        db.rollback(); return 'duplicate'
    count = db.execute("SELECT count(*) FROM events WHERE account=? AND thread=? AND author=? AND status IN ('sent','sending','uncertain')", (account,thread,author)).fetchone()[0]
    if dry_run:
        count += db.execute("SELECT count(*) FROM dry_runs WHERE account=? AND thread=? AND author=? AND status='would_reply'",(account,thread,author)).fetchone()[0]
    if followup:
        root = db.execute('SELECT status FROM events WHERE account=? AND comment=?',(account,thread)).fetchone()
        if dry_run and not root:
            root = db.execute('SELECT status FROM dry_runs WHERE account=? AND comment=?',(account,thread)).fetchone()
        if not root or root[0] not in ('sent','sending','uncertain','would_reply'): count += 1
    rotation = db.execute('SELECT value FROM rotations WHERE account=?',(account,)).fetchone()
    n = rotation[0] if rotation else 0
    if dry_run:
        n += db.execute('SELECT count(*) FROM dry_runs WHERE account=?',(account,)).fetchone()[0]
    decision = respond(text, brand=brand, rotation=n, catalog=catalog)
    try:
        import crisis_safety
        if crisis_safety.is_crisis(text, crisis_safety.build_crisis_keywords(crisis_safety.load_config()), None):
            decision = dict(decision, action='review', reason='existing_crisis_guard', text='')
    except ImportError:
        pass  # portable engine has its own fail-closed sensitive routing
    status = decision['action']
    reason = decision.get('reason','')
    if already_handled and status != 'review': status, reason = 'ignore','already_handled_live'
    if prior and status != 'review': status, reason = 'ignore','page_already_replied'
    if count >= 2 and status != 'review': status, reason = 'ignore','followup_limit'
    if not author: status, reason = 'review','unknown_author'
    reply = decision.get('text','') if status == 'reply' else ''
    if dry_run:
        final = 'would_reply' if status == 'reply' else status
        db.execute('INSERT INTO dry_runs VALUES (?,?,?,?,?,?,?,?,?)',(account,comment,thread,author,final,reason,reply,hashlib.sha256(text.encode()).hexdigest(),datetime.now(timezone.utc).isoformat()))
        db.commit()
        return final
    db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',(account,comment,thread,author,'sending' if status=='reply' else status,reason,reply,datetime.now(timezone.utc).isoformat()))
    db.execute('INSERT OR REPLACE INTO rotations VALUES (?,?)',(account,n+1))
    db.commit()
    if status != 'reply': return status
    try:
        receipt = send(reply)
        final = 'sent' if receipt.get('id') else 'uncertain'
    except Exception:
        final = 'uncertain'
    db.execute('UPDATE events SET status=? WHERE account=? AND comment=?',(final,account,comment)); db.commit()
    return final

def run_accounts(config, dry_run=False, preview=False):
    initialize_persistent_controls()
    controls = json.loads(CONTROL.read_text())
    catalog_path = HERE / 'nv_community_catalog.json'
    catalog = json.loads(catalog_path.read_text()).get('products',[]) if catalog_path.exists() else []
    db = connect()
    legacy = set(controls['accounts'])  # owned accounts never fall into paid/DM path
    results = {}
    for client in config.get('facebook_clients',[]):
        account = str(client['page_id']); rule = controls['accounts'].get(account)
        if not rule: continue
        if preview and not rule.get('dry_run_enabled',False): results[account]='preview_not_enabled'; continue
        if rule.get('paused',True) and not preview: results[account]='paused'; continue
        token = client['page_access_token']
        try:
            identity = graph('GET', 'me', token, fields='id,name,link')
            if str(identity.get('id','')) != account:
                raise GraphError('token_principal_mismatch')
            if identity.get('name','').strip() not in {n.strip() for n in rule['verified_names']}:
                raise GraphError('account_identity_mismatch')
            if dry_run: results[account]='identity_verified_read_only'; continue
            since = int((datetime.now(timezone.utc)-timedelta(hours=48)).timestamp())
            sent=0;previewed=0
            for post in pages(account+'/posts', token, fields='id', since=since, limit=25):
                for comment in pages(post['id']+'/comments', token, fields='id,from,message', limit=50):
                    cid=comment['id']
                    replies=list(pages(cid+'/comments',token,fields='id,from,message',limit=50))
                    own=any(str(x.get('from',{}).get('id'))==account for x in replies)
                    candidates=[(comment,own)]
                    if own: candidates.extend((x,False) for x in replies if str(x.get('from',{}).get('id'))!=account)
                    for item, prior in candidates:
                        author=str(item.get('from',{}).get('id',''))
                        if author==account: continue
                        result=dispatch(db,account,item['id'],cid,author,item.get('message',''),rule['brand'],lambda message: graph('POST', item['id']+'/comments',token,message=message),prior=prior,followup=item['id']!=cid,catalog=catalog,dry_run=preview)
                        if preview and result != 'preview_duplicate': previewed+=1
                        if result=='sent': sent+=1; time.sleep(2)
                        if result=='uncertain': raise GraphError('uncertain_delivery_review')
                        if sent>=20 or previewed>=20: break
                    if sent>=20 or previewed>=20: break
                if sent>=20 or previewed>=20: break
            results[account]=('preview_recorded_'+str(previewed)) if preview else 'checked_sent_'+str(sent)
        except (GraphError, requests.RequestException, ValueError) as exc:
            results[account]=str(exc) if isinstance(exc,GraphError) else 'network_or_payload_error'
        db.execute('INSERT OR REPLACE INTO health VALUES (?,?,?)',(account,results[account],datetime.now(timezone.utc).isoformat()));db.commit()
    db.close()
    return legacy,results

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--check',action='store_true');mode.add_argument('--preview',action='store_true')
    parser.add_argument('--config',type=Path,default=HERE/'review_bot_config.json')
    args=parser.parse_args()
    config=json.loads(args.config.read_text())
    results={'facebook':run_accounts(config,dry_run=args.check,preview=args.preview)[1]}
    from nv_community_native_runtime import run_native_accounts
    results['native']=run_native_accounts(read_only=args.check,preview=args.preview)
    print(json.dumps(results,indent=2))
