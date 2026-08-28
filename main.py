#!/usr/bin/env python3
"""
main.py — Railway bot runner for Lyra-Sha AI / NovaVerse bots.

Reads config from environment variables and runs:
  - comment_bot   every 30 min (at :00 and :30)
  - review_bot    every hour   (at :05)
  - daily_leads   every day    at 8am Mountain Time
"""

import json
import hashlib
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

MOUNTAIN = pytz.timezone("America/Denver")
HERE = Path(__file__).parent
_FB_SENSITIVE_QUERY_RE = re.compile(
    r"([?&](?:access_token|fb_exchange_token|client_secret)=)[^&\s]+",
    re.IGNORECASE,
)


def _redact_facebook_secret(value, *secrets):
    """Remove Facebook secrets and sensitive query values before logging."""
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(str(secret), "[REDACTED]")
    return _FB_SENSITIVE_QUERY_RE.sub(r"\1[REDACTED]", text)


def _write_fb_refresh_receipt(trigger, result, clients=None, valid_count=0,
                              persistence="NOT_ATTEMPTED", reload_id=""):
    """Write only non-secret maintenance evidence to the Railway volume."""
    clients = clients or []
    page_ids = sorted(str(client.get("page_id", "")) for client in clients)
    expiries = sorted(str(client.get("token_expires", "")) for client in clients)
    generation = hashlib.sha256(json.dumps(
        {"page_ids": page_ids, "expiries": expiries},
        sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()[:16]
    receipt = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "trigger": trigger,
        "credential_config_generation": generation,
        "intended_page_count": len(clients),
        "successful_page_count": valid_count,
        "refresh_result": result,
        "persistence_result": persistence,
        "reload_identifier": reload_id,
    }
    receipt_dir = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", str(HERE)))
    receipt_path = receipt_dir / "facebook_refresh_receipt.json"
    try:
        receipt_dir.mkdir(parents=True, exist_ok=True)
        temp_path = receipt_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(receipt, indent=2) + "\n")
        os.replace(temp_path, receipt_path)
        log.info("Facebook maintenance receipt written: result=%s pages=%d/%d persistence=%s",
                 result, valid_count, len(clients), persistence)
    except Exception as exc:
        log.error("Facebook maintenance receipt write failed: %s", exc)


def write_config():
    """Write BOT_CONFIG_JSON env var to review_bot_config.json so bots can read it."""
    raw = os.environ.get("BOT_CONFIG_JSON", "")
    if not raw:
        log.error("BOT_CONFIG_JSON env var not set — bots cannot run without config.")
        sys.exit(1)
    config_path = HERE / "review_bot_config.json"
    with open(config_path, "w") as f:
        f.write(raw)
    log.info(f"Config written to {config_path}")

    # Also write places_config.json for daily_leads
    places_key = os.environ.get("PLACES_API_KEY", "")
    if places_key:
        places_path = HERE / "places_config.json"
        with open(places_path, "w") as f:
            json.dump({"api_key": places_key}, f)
        log.info("Places API key written.")

    # Railway cannot complete an interactive Google sign-in. Recreate any
    # previously authorized OAuth files from protected Railway variables.
    for env_name, filename in (
        ("GOOGLE_CREDENTIALS_JSON", "google_credentials.json"),
        ("GOOGLE_TOKEN_JSON", "google_token.json"),
    ):
        value = os.environ.get(env_name, "").strip()
        if not value:
            continue
        try:
            json.loads(value)
        except json.JSONDecodeError as exc:
            log.error(f"{env_name} is not valid JSON: {exc}")
            continue
        path = HERE / filename
        path.write_text(value)
        path.chmod(0o600)
        log.info(f"{filename} written from {env_name}.")


def init_leads_db():
    """Initialize the SQLite DB with schema and daily targets for daily_leads.py."""
    import sqlite3
    # Persist leads on the Railway volume so daily-sourced leads survive redeploys.
    data_dir = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", str(HERE)))
    db_path = data_dir / "client_hub.db"
    os.environ["CLIENT_HUB_DB"] = str(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name TEXT NOT NULL,
            phone         TEXT DEFAULT '',
            website       TEXT DEFAULT '',
            rating        REAL DEFAULT 0,
            review_count  INTEGER DEFAULT 0,
            maps_url      TEXT DEFAULT '',
            city          TEXT DEFAULT '',
            state         TEXT DEFAULT '',
            status        TEXT DEFAULT 'new',
            dm_text       TEXT DEFAULT '',
            notes         TEXT DEFAULT '',
            last_contact  TEXT DEFAULT '',
            created_at    TEXT DEFAULT (datetime('now','localtime')),
            updated_at    TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS daily_targets (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            biz_type     TEXT NOT NULL,
            city         TEXT NOT NULL,
            state        TEXT NOT NULL,
            max_per_run  INTEGER DEFAULT 10,
            active       INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS activity (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id     INTEGER,
            action      TEXT,
            detail      TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        );
    """)

    # Reconcile daily targets from env var (env var = source of truth).
    # Now that the leads DB persists on a volume, we re-sync on each boot so target
    # updates take effect on redeploy instead of being ignored once the table is non-empty.
    targets_json = os.environ.get("DAILY_TARGETS_JSON", "").strip()
    if targets_json:
        try:
            targets = json.loads(targets_json)
            conn.execute("DELETE FROM daily_targets")
            for t in targets:
                conn.execute(
                    "INSERT INTO daily_targets (biz_type, city, state, max_per_run) VALUES (?,?,?,?)",
                    (t["biz_type"], t["city"], t["state"], t.get("max_per_run", 10))
                )
            conn.commit()
            log.info(f"Synced {len(targets)} daily targets from env var.")
        except Exception as e:
            log.error(f"Failed to sync daily targets: {e}")
    else:
        count = conn.execute("SELECT COUNT(*) FROM daily_targets WHERE active=1").fetchone()[0]
        log.info(f"No DAILY_TARGETS_JSON set; DB has {count} active targets.")

    conn.close()


def run_script(script_name, label):
    log.info(f"▶  Running {label}...")
    script = HERE / script_name
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(HERE),
    )
    output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    if result.returncode != 0:
        log.error(f"❌  {label} failed (exit {result.returncode})")
        if output:
            for line in output.splitlines()[-15:]:
                log.error("   %s", _redact_facebook_secret(line))
        raise RuntimeError(f"{label} failed with exit code {result.returncode}")

    lowered = output.lower()
    skipped = "disabled" in lowered and "skipping" in lowered
    partial = "google reviews skipped" in lowered
    if skipped:
        log.info(f"⏭️  {label} skipped (disabled in configuration)")
    elif partial:
        log.warning(f"⚠️  {label} completed with Google reviews skipped; see details below")
    else:
        log.info(f"✅  {label} completed")
    if output:
        for line in output.splitlines()[-10:]:
            log.info("   %s", _redact_facebook_secret(line))
    return "skipped" if skipped else "partial" if partial else "completed"


def run_comment_bot():
    run_script("comment_bot.py", "Comment Bot")


def run_review_bot():
    run_script("review_bot.py", "Review Bot")


def run_daily_leads():
    run_script("daily_leads.py", "Daily Lead Sourcer")


def run_reddit_bot():
    run_script("reddit_bot.py", "Reddit Bot")


def run_yelp_bot():
    run_script("yelp_bot.py", "Yelp Bot")


def run_review_request_server():
    """Start the Review Request Bot Flask server in a background thread."""
    try:
        from review_request_bot import app, init_db
        import datetime as _dt
        init_db()

        port = int(os.environ.get("PORT", 5001))
        log.info(f"🚀 Review Request Bot starting on port {port}")
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as e:
        log.error(f"Review Request Bot failed to start: {e}")


def auto_refresh_fb_tokens(trigger="startup"):
    """
    Silently extend Facebook tokens if they expire within 14 days or if
    Facebook rejects the stored Page token.
    Runs at startup and daily at 8:05am. No browser needed.
    If tokens are dead (can't be refreshed), logs the error — health check catches it.
    """
    cfg_path = HERE / "review_bot_config.json"
    try:
        cfg        = json.loads(cfg_path.read_text())
        app_id     = cfg.get("facebook_app", {}).get("app_id")
        app_secret = cfg.get("facebook_app", {}).get("app_secret")
        user_token = cfg.get("facebook_user_token")

        if not all([app_id, app_secret, user_token]):
            log.warning("⚠️  FB auto-refresh: missing app credentials — skipping")
            _write_fb_refresh_receipt(trigger, "SKIPPED_MISSING_CREDENTIALS", clients)
            return

        import requests as _req
        sensitive_values = [app_secret, user_token]

        # Check expiry and live validity for every intended Page. Expiry dates
        # can look healthy even after Meta invalidates tokens, so verify both.
        clients    = cfg.get("facebook_clients", [])
        exp_str    = clients[0].get("token_expires", "") if clients else ""
        days_left  = 999
        if exp_str:
            import datetime as _dt
            exp_date  = _dt.datetime.strptime(exp_str[:10], "%Y-%m-%d").date()
            days_left = (exp_date - _dt.date.today()).days

        valid_count = 0
        if clients:
            for client in clients:
                page_id = str(client.get("page_id", ""))
                page_token = client.get("page_access_token", "")
                if page_id and page_token:
                    try:
                        check = _req.get(
                            f"https://graph.facebook.com/v19.0/{page_id}",
                            params={"fields": "id,name"},
                            headers={"Authorization": f"Bearer {page_token}"},
                            timeout=8,
                        )
                        data = check.json() if check.content else {}
                        if check.status_code == 200 and data.get("id") == page_id and "error" not in data:
                            valid_count += 1
                    except Exception as e:
                        log.warning("⚠️  FB token live check failed: %s", _redact_facebook_secret(e, page_token, *sensitive_values))
        token_valid = bool(clients) and valid_count == len(clients)

        if days_left > 14 and token_valid:
            log.info(f"✅  FB tokens healthy — {days_left} days until expiry and live check passed. No refresh needed.")
            _write_fb_refresh_receipt(trigger, "NO_REFRESH_HEALTHY", clients, valid_count)
            return

        reason = f"{len(clients) - valid_count} invalid live token(s)" if not token_valid else f"expiry in {days_left} days"
        log.info(f"🔄  FB tokens need refresh ({reason}) — auto-refreshing now...")

        # Exchange current token for new 60-day token
        r = _req.post("https://graph.facebook.com/v19.0/oauth/access_token", data={
            "grant_type":        "fb_exchange_token",
            "client_id":         app_id,
            "client_secret":     app_secret,
            "fb_exchange_token": user_token,
        }, timeout=15)

        if not r.ok or "access_token" not in r.json():
            log.error("❌  FB token exchange failed: %s", _redact_facebook_secret(r.text[:200], *sensitive_values))
            log.error("    Session may be invalidated — manual re-auth required.")
            _write_fb_refresh_receipt(trigger, "AUTH_INVALID", clients, valid_count)
            return

        new_user_token = r.json()["access_token"]
        sensitive_values.append(new_user_token)
        cfg["facebook_user_token"] = new_user_token

        # Re-fetch all page tokens
        r2 = _req.get("https://graph.facebook.com/v19.0/me/accounts", params={
            "fields":       "id,name,access_token",
        }, headers={"Authorization": f"Bearer {new_user_token}"}, timeout=15)

        if not r2.ok:
            log.error("❌  Failed to fetch page tokens: %s", _redact_facebook_secret(r2.text[:200], *sensitive_values))
            _write_fb_refresh_receipt(trigger, "REDERIVATION_FAILED", clients, valid_count)
            return

        import datetime as _dt
        pages       = r2.json().get("data", [])
        expires_str = (_dt.date.today() + _dt.timedelta(days=60)).isoformat()

        # Validate the complete intended Page set before replacing anything.
        token_map = {p["id"]: p["access_token"] for p in pages}
        expected_ids = {str(client.get("page_id", "")) for client in clients}
        if not expected_ids.issubset(token_map) or len(token_map) < len(expected_ids):
            log.error("❌  FB refresh returned an incomplete intended Page set (%d/%d); keeping current config.",
                      len(expected_ids & set(token_map)), len(expected_ids))
            _write_fb_refresh_receipt(trigger, "INCOMPLETE_PAGE_SET", clients, valid_count)
            return

        # Merge new tokens back into existing client records (preserve page_name etc.)
        for client in cfg.get("facebook_clients", []):
            pid = str(client.get("page_id", ""))
            if pid in token_map:
                client["page_access_token"] = token_map[pid]
                client["token_expires"]     = expires_str

        cfg_path.write_text(json.dumps(cfg, indent=2))
        log.info(f"✅  FB tokens auto-refreshed — {len(pages)} pages. New expiry: {expires_str}")

        # Also update BOT_CONFIG_JSON env var in memory so future write_config() uses new tokens
        os.environ["BOT_CONFIG_JSON"] = json.dumps(cfg)
        _write_fb_refresh_receipt(trigger, "REFRESHED_LOCAL_ONLY", cfg.get("facebook_clients", []),
                                  len(expected_ids), "NOT_PERSISTED_TO_RAILWAY")

    except Exception as e:
        log.error("❌  FB auto-refresh crashed: %s", _redact_facebook_secret(e, *locals().get("sensitive_values", [])))
        _write_fb_refresh_receipt(trigger, "CRASHED", locals().get("clients", []),
                                  locals().get("valid_count", 0))


def scheduled_fb_token_refresh():
    """Single authoritative Railway scheduler entrypoint for the 08:05 job."""
    auto_refresh_fb_tokens(trigger="scheduled_08:05")


def main():
    log.info("=== Lyra-Sha AI Bot Runner starting ===")
    write_config()
    auto_refresh_fb_tokens(trigger="startup")
    init_leads_db()

    scheduler = BlockingScheduler(timezone=MOUNTAIN)

    # Comment bot: every 30 min
    scheduler.add_job(run_comment_bot, CronTrigger(minute="0,30", timezone=MOUNTAIN),
                      id="comment_bot", name="Comment Bot")

    # Review bot: every hour at :05
    scheduler.add_job(run_review_bot, CronTrigger(minute="5", timezone=MOUNTAIN),
                      id="review_bot", name="Review Bot")

    # Daily leads: 8:00am Mountain every day
    scheduler.add_job(run_daily_leads, CronTrigger(hour=8, minute=0, timezone=MOUNTAIN),
                      id="daily_leads", name="Daily Lead Sourcer")

    # FB token auto-refresh: daily at 8:05am — silently extends tokens before expiry
    scheduler.add_job(scheduled_fb_token_refresh, CronTrigger(hour=8, minute=5, timezone=MOUNTAIN),
                      id="fb_token_refresh", name="FB Token Auto-Refresh")

    # Reddit bot: every 2 hours at :15
    scheduler.add_job(run_reddit_bot, CronTrigger(hour="*/2", minute=15, timezone=MOUNTAIN),
                      id="reddit_bot", name="Reddit Bot")

    # Yelp bot: once daily at 9:20am Mountain
    scheduler.add_job(run_yelp_bot, CronTrigger(hour=9, minute=20, timezone=MOUNTAIN),
                      id="yelp_bot", name="Yelp Bot")

    log.info("Scheduled jobs:")
    log.info("  • Comment Bot  — every :00 and :30")
    log.info("  • Review Bot   — every hour at :05")
    log.info("  • Daily Leads  — 8:00 AM Mountain daily")
    log.info("  • Reddit Bot   — every 2 hours at :15")
    log.info("  • Yelp Bot     — 9:20 AM Mountain daily")
    # Start Review Request Bot web server in background thread
    rrb_thread = threading.Thread(target=run_review_request_server, daemon=True)
    rrb_thread.start()
    log.info("  • Review Request Bot — web server started")

    log.info("Starting scheduler...")

    # A deploy or restart must not automatically send replies or create duplicate
    # leads. Startup checks remain available only when explicitly requested.
    if os.environ.get("RUN_STARTUP_CHECKS", "").lower() in {"1", "true", "yes"}:
        log.warning("RUN_STARTUP_CHECKS enabled — running all bots once now.")
        run_comment_bot()
        run_review_bot()
        run_daily_leads()
        run_reddit_bot()
        run_yelp_bot()
    else:
        log.info("Startup bot runs disabled; jobs will run only on their schedules.")

    scheduler.start()


if __name__ == "__main__":
    main()
