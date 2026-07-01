#!/usr/bin/env python3
"""
review_request_bot.py — Sends personalized review request SMS after a customer visit.

Flow:
  1. Business owner submits customer name + phone via simple web form or API
  2. Claude generates a warm, personalized text message
  3. Customer replies:
     - Positive (yes/happy/sure/love it) → bot sends Google review link
     - Negative (bad/problem/issue/no)   → flags owner, never goes public
  4. All conversations tracked in SQLite

Runs as a Flask web server on Railway.
Twilio handles SMS in/out.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import anthropic
from flask import Flask, request, jsonify, redirect
from twilio.rest import Client as TwilioClient
from twilio.twiml.messaging_response import MessagingResponse

# ── Config ────────────────────────────────────────────────────────────────────

HERE          = Path(__file__).parent
# Persist DBs on the Railway volume (mounted at RAILWAY_VOLUME_MOUNT_PATH, e.g. /data)
# so onboarding + trial data survives redeploys. Falls back to local dir off-Railway.
DATA_DIR      = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", str(HERE)))
DB_PATH       = DATA_DIR / "review_requests.db"
CONFIG_FILE   = HERE / "review_bot_config.json"

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_API_KEY     = os.environ.get("TWILIO_API_KEY", "")
TWILIO_API_SECRET  = os.environ.get("TWILIO_API_SECRET", "")
TWILIO_NUMBER      = os.environ.get("TWILIO_PHONE_NUMBER", "")
CLAUDE_KEY         = os.environ.get("CLAUDE_API_KEY", "")

# Fallback: load from config file if env vars not set
if not CLAUDE_KEY and CONFIG_FILE.exists():
    with open(CONFIG_FILE) as f:
        cfg = json.load(f)
    CLAUDE_KEY     = cfg.get("claude_api_key", "")
    TWILIO_API_KEY = TWILIO_API_KEY    or cfg.get("twilio_api_key", "")
    TWILIO_API_SECRET = TWILIO_API_SECRET or cfg.get("twilio_api_secret", "")
    TWILIO_NUMBER  = TWILIO_NUMBER     or cfg.get("twilio_phone_number", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

app    = Flask(__name__)
claude = anthropic.Anthropic(api_key=CLAUDE_KEY) if CLAUDE_KEY else None
twilio = TwilioClient(TWILIO_API_KEY, TWILIO_API_SECRET, TWILIO_ACCOUNT_SID) if TWILIO_API_KEY and TWILIO_API_SECRET else None


# ── Database ──────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS review_requests (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name   TEXT NOT NULL,
            customer_phone  TEXT NOT NULL,
            business_name   TEXT NOT NULL,
            google_link     TEXT NOT NULL,
            owner_phone     TEXT DEFAULT '',
            status          TEXT DEFAULT 'sent',
            -- status: sent | positive | negative | review_link_sent | flagged
            created_at      TEXT DEFAULT (datetime('now','localtime')),
            updated_at      TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS sms_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            direction   TEXT,   -- inbound | outbound
            from_num    TEXT,
            to_num      TEXT,
            body        TEXT,
            request_id  INTEGER,
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS onboarding_requests (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ref_code      TEXT DEFAULT '',
            service_type  TEXT DEFAULT '',
            business_name TEXT NOT NULL,
            contact_name  TEXT DEFAULT '',
            email         TEXT DEFAULT '',
            phone         TEXT DEFAULT '',
            website       TEXT DEFAULT '',
            google_link   TEXT DEFAULT '',
            facebook_link TEXT DEFAULT '',
            yelp_link     TEXT DEFAULT '',
            plan          TEXT DEFAULT '',
            notes         TEXT DEFAULT '',
            status        TEXT DEFAULT 'new',   -- new | onboarding | live
            created_at    TEXT DEFAULT (datetime('now','localtime'))
        );
    """)
    for statement in (
        "ALTER TABLE onboarding_requests ADD COLUMN ref_code TEXT DEFAULT ''",
        "ALTER TABLE onboarding_requests ADD COLUMN service_type TEXT DEFAULT ''",
    ):
        try:
            conn.execute(statement)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()
    log.info("DB initialized.")


def get_pending_request(customer_phone: str):
    """Find the most recent review request for this phone number."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM review_requests WHERE customer_phone=? AND status='sent' ORDER BY id DESC LIMIT 1",
            (customer_phone,)
        ).fetchone()


def update_request_status(request_id: int, status: str):
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            "UPDATE review_requests SET status=?, updated_at=? WHERE id=?",
            (status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), request_id)
        )


def log_sms(direction, from_num, to_num, body, request_id=None):
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            "INSERT INTO sms_log (direction, from_num, to_num, body, request_id) VALUES (?,?,?,?,?)",
            (direction, from_num, to_num, body, request_id)
        )


# ── Claude helpers ────────────────────────────────────────────────────────────

def generate_request_sms(customer_name: str, business_name: str) -> str:
    """Generate a warm, personalized review request text."""
    if not claude:
        return f"Hi {customer_name}! Thanks for visiting {business_name} — we'd love your feedback! Could you leave us a quick Google review? Reply YES and we'll send you the link. 😊"
    try:
        resp = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            system=(
                "You write warm, friendly SMS review request messages for local businesses. "
                "Keep it under 160 characters. Sound human, not robotic. "
                "Ask if they'd be willing to leave a Google review and tell them to reply YES for the link. "
                "Include a warm emoji. Never start with 'Hi there' — use their name."
            ),
            messages=[{
                "role": "user",
                "content": f"Write a review request SMS for: Customer: {customer_name}, Business: {business_name}"
            }]
        )
        return resp.content[0].text.strip()
    except Exception as e:
        log.warning(f"Claude error: {e}")
        return f"Hi {customer_name}! Thanks for choosing {business_name}! Mind leaving us a quick Google review? Reply YES for the link 😊"


def classify_reply(message: str) -> str:
    """Classify a customer reply as positive, negative, or neutral."""
    positive_words = ["yes", "sure", "ok", "okay", "absolutely", "love", "great", "happy",
                      "definitely", "of course", "sounds good", "will do", "👍", "✅"]
    negative_words = ["no", "bad", "terrible", "awful", "horrible", "never", "worst",
                      "disappointed", "unhappy", "problem", "issue", "complaint", "upset"]

    msg_lower = message.lower().strip()

    if any(w in msg_lower for w in positive_words):
        return "positive"
    if any(w in msg_lower for w in negative_words):
        return "negative"

    # Use Claude for ambiguous cases
    if claude:
        try:
            resp = claude.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=10,
                messages=[{
                    "role": "user",
                    "content": (
                        f'Is this reply to a review request positive or negative? '
                        f'Reply with only "positive" or "negative".\n\nMessage: "{message}"'
                    )
                }]
            )
            result = resp.content[0].text.strip().lower()
            return "positive" if "positive" in result else "negative"
        except:
            pass

    return "positive"  # default assumption


def generate_negative_alert(customer_name: str, business_name: str, message: str) -> str:
    """Generate an alert message for the business owner about a negative reply."""
    return (
        f"⚠️ HEADS UP — {business_name}\n"
        f"{customer_name} replied with a concern:\n"
        f"\"{message}\"\n\n"
        f"Reach out to them directly before this becomes a public review. "
        f"A quick personal call can turn this around. — Lyra-Sha AI"
    )


# ── SMS sending ───────────────────────────────────────────────────────────────

def send_sms(to_number: str, body: str, request_id=None):
    """Send an SMS via Twilio."""
    if not twilio:
        log.warning(f"Twilio not configured — would send to {to_number}: {body[:50]}")
        return False
    try:
        msg = twilio.messages.create(
            body=body,
            from_=TWILIO_NUMBER,
            to=to_number
        )
        log_sms("outbound", TWILIO_NUMBER, to_number, body, request_id)
        log.info(f"✅ SMS sent to {to_number}: {body[:60]}...")
        return True
    except Exception as e:
        log.error(f"❌ SMS failed to {to_number}: {e}")
        return False


# ── API Routes ────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    import datetime as _dt, requests as _req
    info = {"status": "ok", "service": "review_request_bot",
            "db_path": str(DB_PATH),
            "on_volume": str(DB_PATH).startswith("/data"),
            "fb_token_valid": None,
            "fb_token_expires": None,
            "days_until_expiry": None,
            "config_age_hours": None}
    try:
        init_db()
        with sqlite3.connect(str(DB_PATH)) as conn:
            info["onboarding_rows"] = conn.execute(
                "SELECT COUNT(*) FROM onboarding_requests").fetchone()[0]
    except Exception as e:
        info["db_error"] = str(e)
    # leads/targets live in client_hub.db on the same volume
    try:
        leads_db = DATA_DIR / "client_hub.db"
        with sqlite3.connect(str(leads_db)) as c2:
            info["lead_targets"] = c2.execute("SELECT COUNT(*) FROM daily_targets").fetchone()[0]
            info["leads_total"] = c2.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    except Exception as e:
        info["leads_error"] = str(e)
    # FB token health — queried by daily_health_check.py every morning
    try:
        cfg_path = Path(__file__).parent / "review_bot_config.json"
        stat = cfg_path.stat()
        info["config_age_hours"] = round((_dt.datetime.utcnow().timestamp() - stat.st_mtime) / 3600, 1)
        cfg = json.loads(cfg_path.read_text())
        clients = cfg.get("facebook_clients", [])
        if clients:
            exp = clients[0].get("token_expires", "")
            info["fb_token_expires"] = exp
            if exp:
                exp_date = _dt.datetime.strptime(exp[:10], "%Y-%m-%d").date()
                info["days_until_expiry"] = (_dt.date.today() - exp_date).days * -1
            token   = clients[0].get("page_access_token", "")
            page_id = clients[0].get("page_id", "")
            r = _req.get(f"https://graph.facebook.com/v19.0/{page_id}",
                params={"access_token": token, "fields": "name"}, timeout=8)
            data = r.json()
            info["fb_token_valid"] = "error" not in data
            info["fb_page_name"]   = data.get("name", "unknown")
    except Exception as e:
        info["fb_check_error"] = str(e)
    return jsonify(info)


@app.route("/", methods=["GET"])
@app.route("/reviews", methods=["GET"])
def reviews_landing():
    """Landing page for review management service.

    Served at both the bare domain (reviews.lyrashaai.com) and /reviews so
    clients who type the subdomain directly land on the page instead of a 404.
    """
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Review Management for Puerto Rico &amp; Local Business | Lyra-Sha AI</title>
  <meta name="description" content="AI review management for Puerto Rico and U.S. local businesses. Lyra-Sha AI answers your Google, Facebook, and Yelp reviews 24/7 — warm, professional, done for you. Serving San Juan, Ponce, Guayanilla, Aguadilla, and Yauco. Free 30-day trial.">
  <meta name="keywords" content="review management Puerto Rico, manejo de reseñas, AI review responses, Google review replies, reputation management San Juan, Ponce, Guayanilla, Aguadilla, Yauco, gomeras, reseñas de Google, negocios locales Puerto Rico, local business reviews, automated review responses">
  <meta name="robots" content="index, follow">
  <meta name="author" content="Lyra-Sha AI">
  <meta name="geo.region" content="US-PR">
  <meta name="geo.placename" content="San Juan, Ponce, Guayanilla, Aguadilla, Yauco, Puerto Rico">
  <link rel="canonical" href="https://reviews.lyrashaai.com/">
  <meta property="og:type" content="website">
  <meta property="og:title" content="AI Review Management for Puerto Rico &amp; Local Business | Lyra-Sha AI">
  <meta property="og:description" content="Never lose a customer to an unanswered review. AI answers your Google, Facebook &amp; Yelp reviews 24/7. Rooted in Puerto Rico and serving local businesses across the U.S. Free 30-day trial.">
  <meta property="og:url" content="https://reviews.lyrashaai.com/">
  <meta property="og:locale" content="en_US">
  <meta property="og:locale:alternate" content="es_PR">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="AI Review Management for Puerto Rico &amp; Local Business | Lyra-Sha AI">
  <meta name="twitter:description" content="AI answers your Google, Facebook &amp; Yelp reviews 24/7. Rooted in Puerto Rico and serving local businesses across the U.S. Free 30-day trial.">
  <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:'Poppins',sans-serif;background:#0a0a0a;color:#fff;line-height:1.6}
    .hero{background:linear-gradient(135deg,#0a0a0a 0%,#1a0a2e 100%);padding:90px 20px 70px;text-align:center}
    .logo{color:#c9a84c;font-size:14px;letter-spacing:3px;text-transform:uppercase;margin-bottom:20px}
    h1{font-size:clamp(2rem,5vw,3.4rem);font-weight:800;line-height:1.15;margin-bottom:18px;max-width:900px;margin-left:auto;margin-right:auto}
    h1 span{color:#c9a84c}
    .subtitle{font-size:1.1rem;color:#bbb;max-width:620px;margin:0 auto 22px}
    .counter{display:inline-block;background:#0e2a14;border:1px solid #2c7a43;color:#7fe3a0;padding:8px 18px;border-radius:30px;font-size:.9rem;margin-bottom:28px}
    .counter b{color:#fff}
    .cta-btn{background:#c9a84c;color:#0a0a0a;padding:16px 40px;border-radius:50px;font-size:1.1rem;font-weight:700;text-decoration:none;display:inline-block;transition:transform .1s}
    .cta-btn:hover{transform:scale(1.03)}
    .microcopy{color:#888;font-size:.85rem;margin-top:14px}
    .stats{display:flex;justify-content:center;gap:46px;padding:50px 20px;background:#111;flex-wrap:wrap}
    .stat{text-align:center}
    .stat-num{font-size:2.4rem;font-weight:800;color:#c9a84c}
    .stat-label{color:#aaa;font-size:.85rem}
    section.pad{padding:70px 20px;max-width:1000px;margin:0 auto}
    h2{text-align:center;font-size:2rem;margin-bottom:14px}
    .lead{text-align:center;color:#aaa;max-width:640px;margin:0 auto 46px}
    .steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:24px}
    .step{background:#141414;border-radius:16px;padding:28px;border:1px solid #242424}
    .step-num{width:38px;height:38px;background:#c9a84c;color:#0a0a0a;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;margin-bottom:14px}
    .step h3{font-size:1.05rem;margin-bottom:8px}
    .step p{color:#aaa;font-size:.9rem}
    .pricing{background:#120a22;padding:70px 20px}
    .tiers{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px;max-width:1050px;margin:30px auto 0;align-items:stretch}
    .tier{background:#0a0a0a;border-radius:18px;padding:34px 28px;border:1px solid #2a2a2a;display:flex;flex-direction:column;position:relative}
    .tier.pop{border:2px solid #c9a84c;box-shadow:0 0 40px rgba(201,168,76,.15)}
    .badge{position:absolute;top:-13px;left:50%;transform:translateX(-50%);background:#c9a84c;color:#0a0a0a;font-size:.72rem;font-weight:800;padding:5px 16px;border-radius:20px;white-space:nowrap;text-transform:uppercase;letter-spacing:.5px}
    .badge.best{background:#7fe3a0}
    .tier h3{font-size:1.25rem;margin-bottom:6px;color:#c9a84c}
    .tier .tag{color:#999;font-size:.85rem;min-height:38px}
    .price{font-size:3rem;font-weight:800;margin:10px 0 0}
    .price span{font-size:1.1rem;color:#aaa;font-weight:400}
    .setup{color:#9fd8b0;font-size:.82rem;margin-bottom:6px}
    .annual{color:#c9a84c;font-size:.8rem;margin-bottom:18px}
    .features{list-style:none;margin-bottom:26px;text-align:left;flex-grow:1}
    .features li{padding:7px 0;border-bottom:1px solid #1d1d1d;color:#ddd;font-size:.9rem}
    .features li::before{content:"\\2713  ";color:#c9a84c;font-weight:700}
    .tier .cta-btn{width:100%;text-align:center;font-size:1rem;padding:14px}
    .smallprint{text-align:center;color:#777;font-size:.82rem;margin-top:30px;max-width:680px;margin-left:auto;margin-right:auto}
    .proof{background:#0e0e0e}
    .quotes{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:22px}
    .quote{background:#141414;border-left:3px solid #c9a84c;border-radius:10px;padding:22px}
    .quote p{font-style:italic;color:#ddd;margin-bottom:12px}
    .quote .who{color:#c9a84c;font-size:.85rem;font-weight:600}
    .stars{color:#c9a84c;letter-spacing:2px;margin-bottom:10px}
    .faq-item{background:#141414;border-radius:12px;padding:20px 24px;margin-bottom:14px;border:1px solid #222}
    .faq-item h4{color:#c9a84c;font-size:1rem;margin-bottom:6px}
    .faq-item p{color:#bbb;font-size:.9rem}
    .final-cta{background:linear-gradient(135deg,#1a0a2e,#0a0a0a);padding:80px 20px;text-align:center}
    .final-cta h2{font-size:2rem;margin-bottom:12px}
    .final-cta p{color:#aaa;margin-bottom:28px}
    footer{background:#000;padding:24px;text-align:center;color:#555;font-size:.85rem}
    footer a{color:#c9a84c;text-decoration:none}
    .roots{background:#0a0a0a;padding:60px 20px;text-align:center;border-top:1px solid #1d1d1d}
    .roots .flag{font-size:1.6rem;margin-bottom:10px}
    .roots h2{margin-bottom:14px}
    .roots p{color:#bbb;max-width:640px;margin:0 auto;font-size:1rem}
  </style>
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "ProfessionalService",
    "name": "Lyra-Sha AI — Review Management",
    "url": "https://reviews.lyrashaai.com/",
    "image": "https://reviews.lyrashaai.com/",
    "email": "help@lyrashaai.com",
    "description": "AI-powered review and reputation management for local businesses. Lyra-Sha AI answers Google, Facebook, and Yelp reviews 24/7 in a warm, professional voice — fully done for you. Founded by a proud boricua with deep roots in Guayanilla, Puerto Rico.",
    "slogan": "Never lose a customer to an unanswered review again.",
    "priceRange": "$97-$297/mo",
    "areaServed": [
      {"@type": "City", "name": "San Juan", "address": {"@type": "PostalAddress", "addressRegion": "PR", "addressCountry": "US"}},
      {"@type": "City", "name": "Ponce", "address": {"@type": "PostalAddress", "addressRegion": "PR", "addressCountry": "US"}},
      {"@type": "City", "name": "Guayanilla", "address": {"@type": "PostalAddress", "addressRegion": "PR", "addressCountry": "US"}},
      {"@type": "City", "name": "Aguadilla", "address": {"@type": "PostalAddress", "addressRegion": "PR", "addressCountry": "US"}},
      {"@type": "City", "name": "Yauco", "address": {"@type": "PostalAddress", "addressRegion": "PR", "addressCountry": "US"}},
      {"@type": "Country", "name": "United States"}
    ],
    "knowsLanguage": ["en", "es"],
    "founder": {"@type": "Person", "description": "Founder with deep roots in Guayanilla, Puerto Rico"},
    "hasOfferCatalog": {
      "@type": "OfferCatalog",
      "name": "Review Management Plans",
      "itemListElement": [
        {"@type": "Offer", "name": "Starter", "price": "97", "priceCurrency": "USD", "description": "Automatic Google review responses, 24/7."},
        {"@type": "Offer", "name": "Pro", "price": "147", "priceCurrency": "USD", "description": "Google plus Facebook recommendation replies."},
        {"@type": "Offer", "name": "Growth", "price": "297", "priceCurrency": "USD", "description": "All-inclusive: Google, Facebook reviews and comments, Reddit, Yelp, and a review request bot."},
        {"@type": "Offer", "name": "Missed Call Bot", "price": "127", "priceCurrency": "USD", "description": "Missed-call text-back support for local businesses using Twilio."}
      ]
    }
  }
  </script>
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
      {"@type": "Question", "name": "How does the free trial work?", "acceptedAnswer": {"@type": "Answer", "text": "You get 30 days free to see the difference. No credit card to start. Continue if you love it, walk away if not."}},
      {"@type": "Question", "name": "Do you serve Puerto Rico and the U.S. territories?", "acceptedAnswer": {"@type": "Answer", "text": "Yes. We work with businesses across all 50 states, Puerto Rico, and U.S. territories, in English and Spanish. We proudly serve San Juan, Ponce, Guayanilla, Aguadilla, and Yauco."}},
      {"@type": "Question", "name": "What is the setup fee for?", "acceptedAnswer": {"@type": "Answer", "text": "It covers building your custom AI voice profile and connecting your platforms, fully done for you within 48 hours. It is a one-time, non-refundable service fee."}},
      {"@type": "Question", "name": "How fast do I go live?", "acceptedAnswer": {"@type": "Answer", "text": "Within 2 to 3 business days of giving us access, often sooner."}},
      {"@type": "Question", "name": "Can I cancel anytime?", "acceptedAnswer": {"@type": "Answer", "text": "Yes. Monthly plans have no contract. Payments already made are non-refundable, but you are never locked in."}}
    ]
  }
  </script>
</head>
<body>
  <section class="hero">
    <div class="logo">Lyra-Sha AI</div>
    <h1>Never Lose a Customer to an <span>Unanswered Review</span> Again.</h1>
    <p class="subtitle">Every review you don't answer quietly costs you customers and drops your ranking. Lyra-Sha AI replies for you &mdash; warm, professional, human-sounding &mdash; 24/7, done for you.</p>
    <div class="counter">🇵🇷 Rooted in Puerto Rico &mdash; serving local businesses in English y español</div><br>
    <a href="/welcome?ref=LSA26ES" class="cta-btn">Start Your Free 30 Days &rarr;</a>
    <p class="microcopy">No credit card to start &middot; Live in 2&ndash;3 business days &middot; Cancel anytime</p>
  </section>

  <section class="stats">
    <div class="stat"><div class="stat-num">24/7</div><div class="stat-label">Automatic Replies</div></div>
    <div class="stat"><div class="stat-num">30</div><div class="stat-label">Days Free Trial</div></div>
    <div class="stat"><div class="stat-num">Fast</div><div class="stat-label">Response Support</div></div>
    <div class="stat"><div class="stat-num">100%</div><div class="stat-label">Done For You</div></div>
  </section>

  <section class="pad">
    <h2>How It Works</h2>
    <p class="lead">No software to learn. No daily logins. You go about your business &mdash; we protect your reputation.</p>
    <div class="steps">
      <div class="step"><div class="step-num">1</div><h3>You give us access</h3><p>A quick one-time setup &mdash; you add us as a manager on your Google &amp; Facebook. Takes about 5 minutes.</p></div>
      <div class="step"><div class="step-num">2</div><h3>Our AI replies for you</h3><p>Every new review gets a warm, genuine response in your business's voice &mdash; within minutes, around the clock.</p></div>
      <div class="step"><div class="step-num">3</div><h3>Your reputation grows</h3><p>More answered reviews = higher ranking, more trust, more customers. You do nothing.</p></div>
    </div>
  </section>

  <section class="pricing">
    <h2>Simple, Honest Pricing</h2>
    <p class="lead">Start with a 30-day free trial. Pay annually and save 10%.</p>
    <div class="tiers">

      <div class="tier">
        <h3>Starter</h3>
        <p class="tag">For businesses that live on Google.</p>
        <div class="price">$97<span>/mo</span></div>
        <div class="setup">+ $149 one-time setup</div>
        <div class="annual">or save 10% paid annually</div>
        <ul class="features">
          <li>Google review responses, 24/7</li>
          <li>Warm, on-brand AI replies</li>
          <li>100% done for you</li>
          <li>Cancel anytime</li>
        </ul>
        <a href="/welcome?ref=LSA26ES" class="cta-btn">Start Free 30 Days</a>
      </div>

      <div class="tier pop">
        <div class="badge">⭐ Most Popular</div>
        <h3>Pro</h3>
        <p class="tag">Google + Facebook, fully covered.</p>
        <div class="price">$147<span>/mo</span></div>
        <div class="setup">+ $199 one-time setup</div>
        <div class="annual">or save 10% paid annually</div>
        <ul class="features">
          <li>Everything in Starter</li>
          <li>Facebook recommendation replies</li>
          <li>Priority response speed</li>
          <li>Cancel anytime</li>
        </ul>
        <a href="/welcome?ref=LSA26ES" class="cta-btn">Start Free 30 Days</a>
      </div>

      <div class="tier">
        <div class="badge best">🏆 Best Value</div>
        <h3>Growth</h3>
        <p class="tag">All-inclusive reputation autopilot.</p>
        <div class="price">$297<span>/mo</span></div>
        <div class="setup">+ $299 one-time setup</div>
        <div class="annual">or save 10% paid annually</div>
        <ul class="features">
          <li>Everything in Pro</li>
          <li>Facebook comment replies</li>
          <li>Reddit mention monitoring + replies</li>
          <li>Yelp review monitoring + reply drafts</li>
          <li>Review Request bot &mdash; turn happy customers into 5-star reviews</li>
          <li>Priority support</li>
        </ul>
        <a href="/welcome?ref=LSA26ES" class="cta-btn">Start Free 30 Days</a>
      </div>

      <div class="tier">
        <h3>Missed Call Bot</h3>
        <p class="tag">For businesses that lose leads when nobody can answer.</p>
        <div class="price">$127<span>/mo</span></div>
        <div class="setup">setup based on phone/Twilio needs</div>
        <div class="annual">no long contract</div>
        <ul class="features">
          <li>Missed-call text-back workflow</li>
          <li>Captures name, number, and what the customer needs</li>
          <li>Owner notification after the missed call</li>
          <li>Good fit for salons, restaurants, shops, gomeras, and service businesses</li>
        </ul>
        <a href="/welcome?ref=LSA26ES" class="cta-btn">Start Missed Call Setup</a>
      </div>

    </div>
    <p class="smallprint">The one-time setup fee covers your custom AI voice profile and full platform integration &mdash; done for you within 48 hours. Setup fee is non-refundable. Monthly plans can be cancelled anytime; no refunds on payments already made.</p>
  </section>

  <section class="pad proof">
    <h2>What Owners Are Saying</h2>
    <p class="lead" style="color:#777;font-size:.85rem">Illustrative examples &mdash; real client results will be featured here as they come in.</p>
    <div class="quotes">
      <div class="quote"><div class="stars">★★★★★</div><p>"Every review finally gets a thoughtful reply, even when the shop is busy."</p><div class="who">Example: local salon owner</div></div>
      <div class="quote"><div class="stars">★★★★★</div><p>"The missed-call text-back means fewer people disappear before we can call them back."</p><div class="who">Example: local service business</div></div>
      <div class="quote"><div class="stars">★★★★★</div><p>"I'm not a writer. This makes my business sound professional without adding another task to my day."</p><div class="who">Example: independent contractor</div></div>
    </div>
  </section>

  <section class="pad">
    <h2>Questions, Answered</h2>
    <div class="faq-item"><h4>How does the free trial work?</h4><p>You get 30 days free to see the difference. No credit card to start. If you love it, you continue &mdash; if not, walk away, no harm done.</p></div>
    <div class="faq-item"><h4>Do you serve Puerto Rico and the U.S. territories?</h4><p>Yes &mdash; proudly. We work with businesses across all 50 states, Puerto Rico, and U.S. territories, in English and Spanish.</p></div>
    <div class="faq-item"><h4>What's the setup fee for?</h4><p>It covers building your custom AI voice profile and connecting your platforms &mdash; fully done for you within 48 hours. It's a one-time, non-refundable service fee.</p></div>
    <div class="faq-item"><h4>How fast do I go live?</h4><p>Within 2&ndash;3 business days of giving us access. Often sooner &mdash; we'd rather under-promise and over-deliver.</p></div>
    <div class="faq-item"><h4>Can I cancel?</h4><p>Anytime. Monthly plans have no contract. Payments already made are non-refundable, but you'll never be locked in.</p></div>
  </section>

  <section class="roots">
    <div class="flag">🇵🇷</div>
    <h2>Rooted in Puerto Rico, serving local businesses across the U.S.</h2>
    <p>Lyra-Sha AI was founded by a proud <em>boricua</em> with deep roots in <strong>Guayanilla, Puerto Rico</strong> &mdash; built to help local businesses across the island, Colorado, Wyoming, and the mainland get the respect their reputation deserves. From <strong>gomeras</strong> in Yauco to salons, restaurants, and service businesses in any state, we answer your reviews in English <em>y en español</em> &mdash; so every customer feels heard. <em>Tu reputación, en buenas manos.</em></p>
  </section>

  <section class="final-cta">
    <h2>Ready to Stop Losing Customers?</h2>
    <p>30 days free. Live in 2&ndash;3 days. Cancel anytime.</p>
    <a href="/welcome?ref=LSA26ES" class="cta-btn">Start Your Free 30 Days &rarr;</a>
    <p class="microcopy">Questions? <a href="mailto:help@lyrashaai.com" style="color:#c9a84c">help@lyrashaai.com</a></p>
  </section>
  <footer>&copy; 2026 Lyra-Sha AI &middot; lyrashaai.com &middot; <a href="mailto:help@lyrashaai.com">help@lyrashaai.com</a></footer>
</body>
</html>"""
    return html, 200, {'Content-Type': 'text/html'}


@app.route("/welcome", methods=["GET"])
def onboarding_page():
    """Post-payment onboarding page: sets the 2-3 day expectation, explains
    access steps, and collects the client's business details."""
    submitted = request.args.get("done") == "1"
    if submitted:
        body = """
        <div class="card center">
          <h1>You're all set! 🎉</h1>
          <p class="big">We've got everything we need. Your AI review service will be
          <strong>live within 2&ndash;3 business days.</strong></p>
          <p>We'll email you the moment it's active. While you wait, please make sure
          you've added us as a manager on the accounts below — that's the only thing
          that can hold up your go-live.</p>
          <a class="btn" href="/welcome">&larr; Back to the steps</a>
        </div>"""
    else:
        body = """
        <div class="card">
          <h1>Welcome to Lyra-Sha AI 👋</h1>
          <p class="big">You're in! Here's exactly what happens next.</p>
          <div class="promise">⏱️ Your service goes <strong>live within 2&ndash;3 business days</strong>
          of receiving access. (Often faster &mdash; we'd rather under-promise and over-deliver.)</div>

          <h2>Step 1 — Give us access (one time, ~5 min)</h2>
          <p>We can only reply to your reviews once you add us as a manager. Pick the ones you use:</p>
          <ul class="steps">
            <li><strong>Google Business Profile:</strong> business.google.com &rarr; Businesses &rarr; your business
              &rarr; <em>Business Profile settings &rarr; People and access &rarr; Add</em> &rarr;
              invite <strong>help@lyrashaai.com</strong> as <em>Manager</em>.</li>
            <li><strong>Facebook Page:</strong> Page &rarr; Settings &rarr; <em>Page access</em> &rarr;
              add a new person &rarr; invite <strong>help@lyrashaai.com</strong> with full access.</li>
            <li><strong>Yelp (optional):</strong> biz.yelp.com &rarr; Account Settings &rarr; Users
              &rarr; add <strong>help@lyrashaai.com</strong>.</li>
          </ul>

          <h2>Step 2 — Tell us about your business</h2>
          <form method="POST" action="/onboard">
            <label>Referral / promo code (optional)<input id="ref_code" name="ref_code" placeholder="LSA26ES"></label>
            <label>What are you starting?
              <select name="service_type" required>
                <option value="">Select…</option>
                <option>Review Bot</option>
                <option>Missed Call Bot</option>
                <option>Review Bot + Missed Call Bot</option>
              </select>
            </label>
            <label>Business name *<input name="business_name" required></label>
            <label>Your name *<input name="contact_name" required></label>
            <label>Email *<input name="email" type="email" required></label>
            <label>Phone<input name="phone"></label>
            <label>Website<input name="website" placeholder="https://"></label>
            <label>Google Business Profile link<input name="google_link" placeholder="https://"></label>
            <label>Facebook Page link<input name="facebook_link" placeholder="https://"></label>
            <label>Yelp page link (optional)<input name="yelp_link" placeholder="https://"></label>
            <label>Your plan
              <select name="plan">
                <option value="">Select…</option>
                <option>Review Starter — $97/month</option>
                <option>Review Pro — $147/month</option>
                <option>Review Growth — $297/month</option>
                <option>Missed Call Bot — $127/month</option>
                <option>Review + Missed Call Bundle</option>
              </select>
            </label>
            <label>Anything we should know?<textarea name="notes" rows="3"></textarea></label>
            <button class="btn" type="submit">Submit &amp; Start My Setup &rarr;</button>
          </form>
        </div>"""

    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome | Lyra-Sha AI</title>
    <style>
      *{{box-sizing:border-box}} body{{font-family:'Poppins',-apple-system,Segoe UI,sans-serif;
      background:#0a0a0a;color:#eee;margin:0;padding:24px;line-height:1.6}}
      .card{{max-width:680px;margin:0 auto;background:#141414;border:1px solid #262626;
      border-radius:16px;padding:32px}} .center{{text-align:center}}
      h1{{color:#c9a84c;margin-top:0}} h2{{color:#c9a84c;font-size:1.15rem;margin-top:28px}}
      .big{{font-size:1.1rem;color:#ddd}}
      .promise{{background:#1a0a2e;border:1px solid #c9a84c;border-radius:10px;
      padding:14px;margin:18px 0;color:#fff}}
      .steps li{{margin-bottom:12px;color:#cfcfcf}} .steps em{{color:#c9a84c;font-style:normal}}
      label{{display:block;margin:14px 0;color:#bbb;font-size:.9rem}}
      input,select,textarea{{width:100%;margin-top:6px;padding:11px;border-radius:8px;
      border:1px solid #333;background:#0e0e0e;color:#fff;font-size:1rem}}
      .btn{{display:inline-block;margin-top:18px;background:#c9a84c;color:#0a0a0a;
      padding:14px 28px;border:none;border-radius:50px;font-size:1rem;font-weight:700;
      text-decoration:none;cursor:pointer}}
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700;800&display=swap" rel="stylesheet">
    </head><body>{body}
    <script>
      (function () {{
        var params = new URLSearchParams(window.location.search);
        var ref = params.get("ref") || params.get("REF");
        if (ref) {{
          try {{ localStorage.setItem("lsa_ref", ref); }} catch (e) {{}}
        }} else {{
          try {{ ref = localStorage.getItem("lsa_ref"); }} catch (e) {{}}
        }}
        if (ref) {{
          var field = document.getElementById("ref_code");
          if (field) field.value = ref;
        }}
      }})();
    </script></body></html>"""
    return html, 200, {"Content-Type": "text/html"}


@app.route("/onboard", methods=["POST"])
def onboard_submit():
    """Save a new client's onboarding details, then show the 2-3 day confirmation."""
    f = request.form
    if not f.get("business_name"):
        return "Business name required.", 400
    try:
        init_db()
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                """INSERT INTO onboarding_requests
                   (ref_code, service_type, business_name, contact_name, email, phone, website,
                    google_link, facebook_link, yelp_link, plan, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (f.get("ref_code",""), f.get("service_type",""), f.get("business_name",""), f.get("contact_name",""), f.get("email",""),
                 f.get("phone",""), f.get("website",""), f.get("google_link",""),
                 f.get("facebook_link",""), f.get("yelp_link",""), f.get("plan",""),
                 f.get("notes","")),
            )
        log.info(f"🆕  Onboarding submitted: {f.get('business_name')} ({f.get('service_type')} / {f.get('plan')}) ref={f.get('ref_code')}")
    except Exception as e:
        log.error(f"onboard_submit error: {e}")
    return redirect("/welcome?done=1")


@app.route("/admin/leads", methods=["GET"])
def admin_leads():
    """Read-only access to client_hub.db leads. Filterable by city / no-website / biz_type.
    Key is a Railway env var ADMIN_LEADS_KEY (or falls back to lyra-clean-2026 if not set)."""
    expected_key = os.environ.get("ADMIN_LEADS_KEY", "lyra-clean-2026")
    if request.args.get("key") != expected_key:
        return "forbidden", 403

    city = request.args.get("city", "").strip()
    state = request.args.get("state", "").strip()
    no_website = request.args.get("no_website", "").lower() in ("1", "true", "yes")
    biz_type = request.args.get("biz_type", "").strip()
    has_phone = request.args.get("has_phone", "").lower() in ("1", "true", "yes")
    limit = min(int(request.args.get("limit", "50")), 500)
    fmt = request.args.get("format", "json")

    try:
        leads_db = DATA_DIR / "client_hub.db"
        with sqlite3.connect(str(leads_db)) as conn:
            conn.row_factory = sqlite3.Row
            where = ["1=1"]
            params = []
            if city:
                where.append("LOWER(city) LIKE ?")
                params.append(f"%{city.lower()}%")
            if state:
                where.append("LOWER(state) = ?")
                params.append(state.lower())
            if no_website:
                where.append("(website IS NULL OR website = '')")
            if biz_type:
                # Check leads.biz_type if present (lyra_builds bot), else look at row dump
                where.append("(business_name LIKE ? OR dm_text LIKE ?)")
                params.append(f"%{biz_type}%")
                params.append(f"%{biz_type}%")
            if has_phone:
                where.append("phone IS NOT NULL AND phone != ''")

            # Filter out previously-contacted leads
            where.append("(status IS NULL OR status NOT IN ('contacted','converted','declined','spam'))")

            sql = f"""SELECT id, business_name, phone, website, city, state,
                            rating, review_count, maps_url, status, dm_text, notes,
                            created_at, last_contact
                     FROM leads WHERE {' AND '.join(where)}
                     ORDER BY review_count DESC, rating DESC LIMIT ?"""
            params.append(limit)
            rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

            # Get total counts for context
            total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            no_site_total = conn.execute(
                "SELECT COUNT(*) FROM leads WHERE (website IS NULL OR website = '')"
            ).fetchone()[0]
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if fmt == "json":
        return jsonify({
            "filters_applied": {"city": city, "state": state, "no_website": no_website,
                                "biz_type": biz_type, "limit": limit},
            "total_in_db": total,
            "total_no_website": no_site_total,
            "returned": len(rows),
            "leads": rows,
        })

    # CSV format
    if fmt == "csv":
        import csv
        from io import StringIO
        if not rows:
            return "", 200, {"Content-Type": "text/csv"}
        buf = StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
        return buf.getvalue(), 200, {"Content-Type": "text/csv",
                                     "Content-Disposition": "attachment; filename=lyra_leads.csv"}

    return jsonify({"error": "unknown format"}), 400


@app.route("/admin/clear-tests", methods=["GET"])
def clear_tests():
    """One-off cleanup: remove test/demo onboarding rows. Guarded by a key."""
    if request.args.get("key") != "lyra-clean-2026":
        return "forbidden", 403
    try:
        init_db()
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.execute(
                "DELETE FROM onboarding_requests WHERE "
                "business_name LIKE '%TEST%' OR business_name LIKE '%PROOF%' "
                "OR business_name LIKE '%DEMO%'")
            deleted = cur.rowcount
            remaining = conn.execute("SELECT COUNT(*) FROM onboarding_requests").fetchone()[0]
        return jsonify({"deleted": deleted, "remaining": remaining})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/trials", methods=["GET"])
def trials_tracker():
    """Trial tracker: every onboarded client, their day-25 nudge date and day-30
    trial end, with a flag when the conversion message is due."""
    from datetime import datetime, timedelta
    MONTHLY = {
        "Starter": "$97", "Pro": "$147", "Growth": "$297",
        "Review Starter — $97/month": "$97",
        "Review Pro — $147/month": "$147",
        "Review Growth — $297/month": "$297",
        "Missed Call Bot — $127/month": "$127",
        "Review + Missed Call Bundle": "bundle"
    }
    try:
        init_db()
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM onboarding_requests ORDER BY id DESC LIMIT 200").fetchall()]
    except Exception as e:
        log.warning(f"trials_tracker error: {e}")
        rows = []

    today = datetime.now().date()
    cards = ""
    due = 0
    for r in rows:
        try:
            start = datetime.strptime(r["created_at"][:10], "%Y-%m-%d").date()
        except Exception:
            start = today
        day25 = start + timedelta(days=25)
        day30 = start + timedelta(days=30)
        status = r.get("status", "new")
        is_due = today >= day25 and status not in ("converted", "active", "cancelled")
        flag = ""
        if is_due:
            due += 1
            flag = "<span class='due'>🔔 SEND DAY-25 MESSAGE</span>"
        cards += f"""
        <div class="row {'hot' if is_due else ''}">
          <div><b>{r['business_name']}</b> &middot; {r.get('service_type') or '—'} &middot; {r['plan'] or '—'} ({MONTHLY.get(r['plan'],'?')}/mo)<br>
            <small>{r['contact_name']} &middot; {r['email']} &middot; {r['phone']}</small></div>
          <div class="dates">Trial start: {start} &nbsp;|&nbsp; <b>Day 25: {day25}</b> &nbsp;|&nbsp; Ends: {day30}<br>
            Status: <b>{status}</b> {flag}</div>
        </div>"""
    if not cards:
        cards = "<p style='color:#888'>No trials yet. Onboarded clients appear here automatically.</p>"

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trial Tracker | Lyra-Sha AI</title>
    <style>body{{font-family:-apple-system,Segoe UI,sans-serif;background:#0a0a0a;color:#eee;padding:24px}}
    h1{{color:#c9a84c}} .sub{{color:#888;margin-bottom:20px}}
    .row{{background:#151515;border:1px solid #262626;border-radius:10px;padding:16px;margin-bottom:10px;
    display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;font-size:.9rem;line-height:1.5}}
    .row.hot{{border-color:#c9a84c;background:#1a1405}}
    .dates{{color:#aaa;text-align:right}}
    .due{{display:inline-block;background:#c9a84c;color:#0a0a0a;font-weight:700;padding:3px 10px;border-radius:6px;font-size:.78rem;margin-left:6px}}
    small{{color:#888}}</style></head><body>
    <h1>Trial Tracker</h1>
    <p class="sub">{len(rows)} client(s) &middot; <b style="color:#c9a84c">{due} due for day-25 conversion message</b>.
    Day 25 is your money moment — send the matching message from conversion_kit.md.</p>
    {cards}
    </body></html>"""
    return html, 200, {"Content-Type": "text/html"}


@app.route("/onboard-admin", methods=["GET"])
def onboard_admin():
    """Internal view of new client signups waiting to be onboarded."""
    try:
        init_db()
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM onboarding_requests ORDER BY id DESC LIMIT 100").fetchall()]
    except Exception as e:
        log.warning(f"onboard_admin error: {e}")
        rows = []
    items = "".join(
        f"<div class='c'><b>{r['business_name']}</b> · {r.get('service_type') or '—'} · {r['plan'] or '—'} · {r['status']}<br>"
        f"{r['contact_name']} · {r['email']} · {r['phone']}<br>"
        f"G: {r['google_link'] or '—'} | FB: {r['facebook_link'] or '—'} | Yelp: {r['yelp_link'] or '—'}<br>"
        f"<small>Referral: {r.get('ref_code') or '—'} · {r['notes']}</small> <small style='color:#666'>· {r['created_at']}</small></div>"
        for r in rows) or "<p style='color:#888'>No signups yet.</p>"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Onboarding Queue</title>
    <style>body{{font-family:sans-serif;background:#0a0a0a;color:#eee;padding:24px}}
    h1{{color:#c9a84c}} .c{{background:#151515;border:1px solid #262626;border-radius:10px;
    padding:14px;margin-bottom:10px;font-size:.9rem;line-height:1.5}}</style></head>
    <body><h1>Onboarding Queue ({len(rows)})</h1>{items}</body></html>"""
    return html, 200, {"Content-Type": "text/html"}


@app.route("/drafts", methods=["GET"])
def drafts_page():
    """Review queue: AI-suggested Reddit/Yelp replies waiting for human posting."""
    try:
        import drafts_store
        drafts_store.init_drafts_db()
        items = drafts_store.list_drafts(status="pending", limit=200)
    except Exception as e:
        log.warning(f"drafts_page error: {e}")
        items = []

    rows = ""
    for d in items:
        badge = "#8B0000" if d["platform"] == "yelp" else "#c9a84c"
        link = (f'<a href="{d["source_url"]}" target="_blank" style="color:#c9a84c">view original ↗</a>'
                if d["source_url"] else "")
        rows += f"""
        <div class="card">
          <div class="meta"><span class="tag" style="background:{badge}">{d['platform'].upper()}</span>
            <strong>{d['client']}</strong> · {d['author']} · {d['created_at']} &nbsp; {link}</div>
          <div class="orig">{d['original_text'][:400]}</div>
          <div class="reply">💬 {d['suggested_reply']}</div>
        </div>"""
    if not rows:
        rows = '<p style="color:#888">No pending drafts yet. Reddit and Yelp drafts will appear here.</p>'

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reply Drafts | Lyra-Sha AI</title>
    <style>
      body{{font-family:-apple-system,Segoe UI,sans-serif;background:#0a0a0a;color:#eee;margin:0;padding:24px}}
      h1{{color:#c9a84c}} .sub{{color:#888;margin-bottom:24px}}
      .card{{background:#151515;border:1px solid #262626;border-radius:12px;padding:16px;margin-bottom:14px}}
      .meta{{font-size:.85rem;color:#aaa;margin-bottom:8px}}
      .tag{{color:#0a0a0a;font-weight:700;padding:2px 8px;border-radius:6px;font-size:.7rem;margin-right:6px}}
      .orig{{color:#bbb;font-style:italic;border-left:3px solid #333;padding-left:10px;margin:8px 0;font-size:.9rem}}
      .reply{{background:#0f1a0f;border:1px solid #1f3a1f;border-radius:8px;padding:10px;color:#d6f5d6}}
    </style></head><body>
    <h1>Reply Drafts</h1>
    <p class="sub">AI-suggested replies for Reddit &amp; Yelp. Copy and post them manually
    (Yelp has no reply API; Reddit is human-reviewed for safety).</p>
    {rows}
    </body></html>"""
    return html, 200, {"Content-Type": "text/html"}


@app.route("/send-request", methods=["POST"])
def send_review_request():
    """
    Endpoint for business owners to trigger a review request.

    POST body (JSON):
    {
        "customer_name":  "Maria Garcia",
        "customer_phone": "+13035551234",
        "business_name":  "Salon Salon Fort Collins",
        "google_link":    "https://g.page/r/XXXXX/review",
        "owner_phone":    "+17198821456"   (optional — for negative alerts)
    }
    """
    data = request.json or {}

    customer_name  = data.get("customer_name", "").strip()
    customer_phone = data.get("customer_phone", "").strip()
    business_name  = data.get("business_name", "").strip()
    google_link    = data.get("google_link", "").strip()
    owner_phone    = data.get("owner_phone", "").strip()

    if not all([customer_name, customer_phone, business_name, google_link]):
        return jsonify({"error": "Missing required fields: customer_name, customer_phone, business_name, google_link"}), 400

    # Save to DB
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.execute(
            "INSERT INTO review_requests (customer_name, customer_phone, business_name, google_link, owner_phone) VALUES (?,?,?,?,?)",
            (customer_name, customer_phone, business_name, google_link, owner_phone)
        )
        request_id = cur.lastrowid

    # Generate and send the SMS
    sms_text = generate_request_sms(customer_name, business_name)
    sent = send_sms(customer_phone, sms_text, request_id)

    log.info(f"📤 Review request #{request_id} → {customer_name} ({customer_phone}) for {business_name}")

    return jsonify({
        "success": sent,
        "request_id": request_id,
        "message_sent": sms_text
    })


_missed_call_db_initialized = False

@app.route("/webhook/missed-call", methods=["POST"])
def missed_call_webhook():
    """Twilio voice webhook for missed call text-back."""
    global _missed_call_db_initialized
    try:
        from missed_call_bot import handle_missed_call, init_missed_call_db
        if not _missed_call_db_initialized:
            init_missed_call_db()
            _missed_call_db_initialized = True
        return handle_missed_call()
    except Exception as e:
        import traceback
        log.error(f"Missed call handler error: {e}\n{traceback.format_exc()}")
        from twilio.twiml.voice_response import VoiceResponse
        r = VoiceResponse()
        r.say("Thanks for calling Lyra Builds! We missed you, but we'll text you right back. Talk soon!", voice="alice")
        r.hangup()
        return str(r), 200, {"Content-Type": "text/xml"}


@app.route("/webhook/inbound-sms", methods=["POST"])
def inbound_sms():
    """
    Twilio webhook — fires when a customer replies to a review request.
    Configure in Twilio console:
    Messaging → Phone Numbers → your number → A MESSAGE COMES IN → Webhook → this URL
    """
    from_number = request.form.get("From", "")
    body        = request.form.get("Body", "").strip()

    log.info(f"📩 Inbound SMS from {from_number}: {body[:80]}")

    twiml = MessagingResponse()

    # Find the pending request for this number
    req = get_pending_request(from_number)

    if not req:
        # No pending request — ignore or send generic response
        log.info(f"No pending request found for {from_number}")
        return str(twiml)

    request_id    = req["id"]
    customer_name = req["customer_name"]
    business_name = req["business_name"]
    google_link   = req["google_link"]
    owner_phone   = req["owner_phone"]

    log_sms("inbound", from_number, TWILIO_NUMBER, body, request_id)

    sentiment = classify_reply(body)
    log.info(f"Sentiment: {sentiment} for request #{request_id}")

    if sentiment == "positive":
        # Send the Google review link
        reply = (
            f"Amazing, thank you {customer_name}! 🙏 "
            f"Here's the link — takes less than a minute: {google_link} "
            f"We really appreciate you! — {business_name}"
        )
        twiml.message(reply)
        update_request_status(request_id, "review_link_sent")
        log.info(f"✅ Review link sent to {customer_name}")

    else:
        # Negative — catch it, thank them, alert owner
        reply = (
            f"We're sorry to hear that, {customer_name}. "
            f"Someone from our team will reach out to you shortly to make it right. "
            f"Thank you for letting us know. — {business_name}"
        )
        twiml.message(reply)
        update_request_status(request_id, "negative")

        # Alert the business owner if we have their number
        if owner_phone:
            alert = generate_negative_alert(customer_name, business_name, body)
            send_sms(owner_phone, alert, request_id)

        log.info(f"⚠️  Negative reply caught for {customer_name} — owner alerted")

    return str(twiml)


@app.route("/dashboard", methods=["GET"])
def dashboard():
    """Simple JSON dashboard of recent review requests."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM review_requests ORDER BY id DESC LIMIT 50"
        ).fetchall()

    stats = {
        "total": len(rows),
        "sent": sum(1 for r in rows if r["status"] == "sent"),
        "positive": sum(1 for r in rows if r["status"] in ("positive", "review_link_sent")),
        "negative": sum(1 for r in rows if r["status"] in ("negative", "flagged")),
    }

    return jsonify({
        "stats": stats,
        "recent": [dict(r) for r in rows[:10]]
    })


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5001))
    log.info(f"🚀 Review Request Bot starting on port {port}")
    log.info(f"   Twilio: {'✅ configured' if twilio else '❌ not configured'}")
    log.info(f"   Claude: {'✅ configured' if claude else '❌ not configured'}")
    app.run(host="0.0.0.0", port=port, debug=False)
