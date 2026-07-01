#!/usr/bin/env python3
"""
yelp_bot.py — Monitors new Yelp reviews and generates ready-to-paste reply drafts.

IMPORTANT — Yelp API limitation (this is a Yelp restriction, not a bug):
  The Yelp Fusion API is READ-ONLY for reviews. There is NO public endpoint to
  POST a reply to a review. Business owners must reply manually in Yelp for
  Business (biz.yelp.com). The API also returns at most 3 (truncated) review
  excerpts per business.

So this bot does the only legitimate thing possible: it pulls recent reviews,
writes a warm Claude-drafted reply for each, and saves it to the drafts store
(/drafts page). Ingrid (or the client) copies the draft and posts it in Yelp
for Business — one click of paste instead of writing from scratch.

Config block (in review_bot_config.json):
{
  "yelp": {
    "enabled": true,
    "api_key": "...",                 # Yelp Fusion API key (fusion.yelp.com)
    "clients": [
      {
        "client": "Acme Salon",
        "business_id": "acme-salon-denver",   # Yelp business id or alias
        "persona": "You represent Acme Salon, an upscale Denver hair salon. Warm, gracious, professional."
      }
    ]
  }
}

Run on its own; main.py schedules it. Requires: requests, anthropic.
"""

import json
import logging
import sys
import time
from pathlib import Path

import anthropic
import requests

import drafts_store

HERE        = Path(__file__).parent
CONFIG_FILE = HERE / "review_bot_config.json"
LOG_FILE    = HERE / "yelp_bot_log.txt"
YELP_BASE   = "https://api.yelp.com/v3"

_handlers = [logging.StreamHandler(sys.stdout)]
try:
    _handlers.append(logging.FileHandler(LOG_FILE))
except OSError:
    pass
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s",
                    handlers=_handlers, datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger(__name__)


def fetch_reviews(api_key, business_id):
    try:
        r = requests.get(
            f"{YELP_BASE}/businesses/{business_id}/reviews",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"limit": 20, "sort_by": "newest"},
            timeout=20,
        )
        if r.status_code == 404:
            log.warning(f"  business '{business_id}' not found on Yelp.")
            return []
        if not r.ok:
            log.warning(f"  Yelp API error {r.status_code}: {r.text[:120]}")
            return []
        return r.json().get("reviews", [])
    except Exception as e:
        log.warning(f"  Yelp fetch failed: {e}")
        return []


def generate_reply(claude, persona, business, rating, review_text):
    tone = ("Thank them warmly and specifically." if rating and rating >= 4
            else "Be gracious, take responsibility, and invite them to make it right offline. "
                 "Never argue or get defensive.")
    try:
        resp = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=180,
            system=(
                persona + "\n\n"
                "You are drafting a public reply to a Yelp review as the business owner. "
                f"{tone} Sound human and sincere, not corporate. No hashtags. "
                "2-4 sentences. Do not invent details you weren't given."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Business: {business}\nStar rating: {rating}\n"
                    f"Review:\n\"{review_text}\"\n\nWrite the owner's reply."
                ),
            }],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        log.warning(f"  Claude error: {e}")
        return None


def main():
    if not CONFIG_FILE.exists():
        log.error("❌  Config not found.")
        return
    cfg = json.loads(CONFIG_FILE.read_text())
    ycfg = cfg.get("yelp")

    if not ycfg or not ycfg.get("enabled"):
        log.info("Yelp bot disabled (no 'yelp' config or enabled=false) — skipping.")
        return
    if not ycfg.get("api_key"):
        log.error("❌  Yelp api_key missing in config.")
        return

    claude = anthropic.Anthropic(api_key=cfg["claude_api_key"])
    drafts_store.init_drafts_db()
    api_key = ycfg["api_key"]

    log.info("🍽️  Yelp bot running — monitor + draft (Yelp API cannot auto-post replies)")
    drafted = 0

    for client in ycfg.get("clients", []):
        business    = client.get("client", "the business")
        business_id = client.get("business_id", "")
        persona     = client.get("persona", f"You represent {business}.")
        if not business_id:
            continue
        log.info(f"\n🔎  {business} (yelp:{business_id})")

        reviews = fetch_reviews(api_key, business_id)
        log.info(f"   {len(reviews)} review(s) returned by Yelp.")

        for rev in reviews:
            source_id = rev.get("id", "")
            text      = (rev.get("text") or "").strip()
            rating    = rev.get("rating")
            author    = (rev.get("user") or {}).get("name", "a customer")
            url       = rev.get("url", "")
            if not source_id or not text:
                continue
            if drafts_store.already_drafted("yelp", source_id):
                continue

            reply = generate_reply(claude, persona, business, rating, text)
            if not reply:
                continue

            drafts_store.save_draft("yelp", business, source_id, reply,
                                    url, author, text)
            drafted += 1
            log.info(f"   📝  draft saved ({rating}★ from {author})")
            time.sleep(1)

    log.info(f"\n🎯  Yelp done — {drafted} reply draft(s) saved for manual posting.")


if __name__ == "__main__":
    main()
