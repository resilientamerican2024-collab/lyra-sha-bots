"""Existing scheduler entrypoint. Private preview by default; explicit per-page live gates."""
import json, os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PILOT = {'813874968486490', '565654433307015'}

def approved_clients(config, controls, requested):
    requested = set(requested)
    if not requested or not requested <= PILOT:
        raise ValueError('pilot_allowlist_required')
    clients = []
    for row in config.get('facebook_clients', []):
        page = str(row['page_id'])
        if page not in requested:
            continue
        rule = controls.get('accounts', {}).get(page, {})
        if rule.get('paused', True) or rule.get('founder_public_replies_approved') is not True:
            raise ValueError('page_approval_missing_or_paused')
        clients.append(row)
    if {str(row['page_id']) for row in clients} != requested:
        raise ValueError('pilot_credentials_missing')
    return {'facebook_clients': clients}

def main():
    source = Path(os.environ.get('COMMUNITY_META_CONFIG_PATH', str(HERE/'review_bot_config.json')))
    if os.environ.get('COMMUNITY_PUBLIC_REPLIES_APPROVED') != 'true':
        return subprocess.run([sys.executable, str(HERE/'nv_community_runtime.py'), '--preview', '--config', str(source)], check=False).returncode
    from nv_community_runtime import CONTROL, initialize_persistent_controls, run_accounts
    initialize_persistent_controls()
    requested = [s.strip() for s in os.environ.get('COMMUNITY_PUBLIC_PAGE_IDS','').split(',') if s.strip()]
    try:
        config = approved_clients(json.loads(source.read_text()), json.loads(CONTROL.read_text()), requested)
    except (OSError, ValueError, KeyError):
        print('Community live dispatch blocked: configuration or approval gate failed', file=sys.stderr)
        return 2
    # Only the allowlisted Facebook accounts; never run legacy or native adapters here.
    _, results = run_accounts(config)
    print(json.dumps({'facebook': results}))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
