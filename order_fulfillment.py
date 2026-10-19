#!/usr/bin/env python3
"""
order_fulfillment.py -- minimal order -> leads -> CSV -> email pipeline.

Flask Blueprint. Disabled unless ORDER_FULFILLMENT_ENABLED=1 (see register()).
Does not touch payments: it only accepts an HMAC-signed order request from
whatever system confirms payment.

Env vars (names only; values live in Railway variables):
  ORDER_WEBHOOK_SECRET      shared secret for HMAC-SHA256 signature (required)
  ORDER_STATUS_KEY          key for GET /order-status/<id> (defaults to webhook secret)
  FULFILLMENT_TEST_RECIPIENTS  comma list; test orders may only email these
                            (default ingrid@lyrashaai.com)
  LEADS_PROVIDER            "osm" (free, default) or "places" (paid Google Places; needs approval)
  PLACES_API_KEY            only used when LEADS_PROVIDER=places
  SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASS SMTP_FROM   email delivery (optional until approved)
  FULFILLMENT_MAX_LEADS     hard cap per order (default 25)
  RAILWAY_VOLUME_MOUNT_PATH data dir (sqlite + csv)

Signature: header X-Lyra-Signature = hex(HMAC_SHA256(secret, raw_body)).
Order JSON: {order_id, customer_email, business_type, city, state, quantity, test}

Statuses: RECEIVED -> PROCESSING -> LEADS_FOUND -> VALIDATED -> CSV_READY ->
          EMAIL_SENT -> FULFILLED.  Failures: FAILED (retryable up to 3),
          DELIVERY_BLOCKED (CSV built but no email credentials; NOT fulfilled).
"""
import csv
import hashlib
import hmac
import io
import json
import logging
import os
import re
import smtplib
import sqlite3
import threading
import time
from email.message import EmailMessage
from pathlib import Path

import requests
from flask import Blueprint, jsonify, request

log = logging.getLogger("order_fulfillment")
bp = Blueprint("order_fulfillment", __name__)

HERE = Path(__file__).resolve().parent
MAX_ATTEMPTS = 3
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CSV_COLUMNS = ["name", "category", "address", "phone", "website", "rating", "review_count", "source", "source_url", "review_flag", "confidence", "source_release", "data_attribution"]


def data_dir():
    d = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", str(HERE))) / "orders"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db():
    c = sqlite3.connect(str(data_dir() / "orders.db"), timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS orders(
            order_id TEXT PRIMARY KEY,           -- uniqueness = replay protection
            customer_email TEXT, business_type TEXT, city TEXT, state TEXT,
            quantity INTEGER, is_test INTEGER, status TEXT, attempts INTEGER DEFAULT 0,
            lead_count INTEGER DEFAULT 0, csv_path TEXT, message_id TEXT,
            last_error TEXT DEFAULT '', created_at TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS order_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, event TEXT, detail TEXT,
            at TEXT DEFAULT (datetime('now')));
        """)


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def event(order_id, ev, detail=""):
    with db() as c:
        c.execute("INSERT INTO order_events(order_id,event,detail) VALUES(?,?,?)", (order_id, ev, str(detail)[:500]))


def set_status(order_id, status, **cols):
    sets = ["status=?", "updated_at=?"] + [f"{k}=?" for k in cols]
    with db() as c:
        c.execute(f"UPDATE orders SET {','.join(sets)} WHERE order_id=?", [status, now(), *cols.values(), order_id])
    event(order_id, status, cols.get("last_error", ""))


# ---------------------------------------------------------------- lead sourcing
def source_osm(btype, city, state, limit):
    """Free provider: OpenStreetMap Overpass. Best-effort, retries with backoff."""
    tags = {"plumber": ['["craft"="plumber"]', '["shop"="plumbing"]', '["office"="plumber"]']}.get(
        btype.lower().strip(), [f'["craft"="{btype.lower()}"]'])
    body = "".join(f"nwr{t}(area.a);" for t in tags)
    q = (f'[out:json][timeout:25];area["name"="{city}"]["boundary"="administrative"]->.a;({body});'
         f"out center tags {limit * 3};")
    last = None
    for i in range(4):
        try:
            r = requests.post("https://overpass-api.de/api/interpreter", data={"data": q}, timeout=40,
                              headers={"User-Agent": "LyraShaFulfillment/0.1 (ingrid@lyrashaai.com)"})
            if r.status_code == 200:
                out = []
                for e in r.json().get("elements", []):
                    t = e.get("tags", {})
                    addr = " ".join(filter(None, [t.get("addr:housenumber"), t.get("addr:street")]))
                    addr = ", ".join(filter(None, [addr, t.get("addr:city", city), t.get("addr:state", state)]))
                    out.append({"name": t.get("name", ""), "address": addr,
                                "phone": t.get("phone") or t.get("contact:phone", ""),
                                "website": t.get("website") or t.get("contact:website", ""),
                                "rating": "", "review_count": "", "source": "OpenStreetMap",
                                "source_url": f"https://www.openstreetmap.org/{e['type']}/{e['id']}",
                                "_city": t.get("addr:city", city), "_closed": "disused" in " ".join(t) or t.get("opening_hours") == "off"})
                return out
            last = f"overpass HTTP {r.status_code}"
        except Exception as ex:  # noqa
            last = str(ex)
        time.sleep(3 * (2 ** i))
    raise RuntimeError(f"OSM lead source unavailable: {last}")


# Niche configuration: NO per-niche code. Unknown business_type falls back to using the text as the search term.
# query = Google search phrase; words = relevance words (any one must appear in the business name or Google's category label).
NICHES = {
    "plumber": {"query": "plumber", "words": ["plumb", "drain", "rooter", "sewer", "pipe", "water heater"]},
    "landscaper": {"query": "landscaping company", "words": ["landscap", "lawn", "yard", "garden", "tree", "sprinkler", "irrigation"]},
    "window installer": {"query": "window installation company", "words": ["window", "glass", "door", "glazing"]},
    "insulation contractor": {"query": "insulation contractor", "words": ["insulat", "spray foam", "energy"]},
    "roofer": {"query": "roofing contractor", "words": ["roof", "shingle", "exterior"]},
    "hvac": {"query": "HVAC contractor", "words": ["hvac", "heating", "cooling", "air condition", "furnace", "mechanical", "refrigerat"]},
    "well driller": {"query": "water well drilling contractor", "words": ["well", "drill", "pump", "water"]},
}
ALIASES = {"plumbers": "plumber", "plumbing": "plumber", "landscapers": "landscaper", "landscaping": "landscaper",
           "window installers": "window installer", "windows": "window installer", "insulation": "insulation contractor",
           "insulation contractors": "insulation contractor", "roofers": "roofer", "roofing": "roofer",
           "hvac company": "hvac", "hvac companies": "hvac", "heating and cooling": "hvac",
           "well drillers": "well driller", "well drilling": "well driller"}


def niche_for(btype):
    k = (btype or "").lower().strip()
    k = ALIASES.get(k, k)
    return NICHES.get(k, {"query": btype, "words": []}), (k if k in NICHES else "custom")


def source_places(btype, city, state, limit):
    """Existing lead_finder.py (Google Places). PAID; only when LEADS_PROVIDER=places. Pages requested = ceil(limit/20)."""
    import lead_finder
    key = os.environ.get("PLACES_API_KEY", "")
    if not key:
        raise RuntimeError("PLACES_API_KEY not set")
    lead_finder.FIELD_MASK = lead_finder.FIELD_MASK + ",places.primaryTypeDisplayName,places.addressComponents"
    niche, _ = niche_for(btype)
    out = []
    for p in lead_finder.search(key, f"{niche['query']} in {city}, {state}", limit):
        r = lead_finder.to_row(p)
        comps = p.get("addressComponents", [])
        locality = next((c.get("longText", "") for c in comps if "locality" in c.get("types", [])), "")
        out.append({"name": r["name"], "address": r["address"], "phone": r["phone"], "website": r["website"],
                    "rating": r["rating"], "review_count": r["review_count"], "source": "Google Places",
                    "source_url": r["google_maps_url"], "_city": locality or city,
                    "_closed": r["status"] in ("CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"),
                    "_category": (p.get("primaryTypeDisplayName") or {}).get("text", ""),
                    "_address_text": r["address"]})
    return out


def find_leads(btype, city, state, limit):
    prov = os.environ.get("LEADS_PROVIDER", "osm").lower()
    if prov == "overture":
        import overture_provider
        return overture_provider.source_overture(btype, city, state, limit, niche_for(btype)[1])
    return (source_places if prov == "places" else source_osm)(btype, city, state, limit)


# ---------------------------------------------------------------- validation
def norm_phone(p):
    d = re.sub(r"\D", "", p or "")
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if len(d) == 10 else ""


def norm_site(w):
    w = (w or "").strip()
    if not w:
        return ""
    if not w.startswith("http"):
        w = "http://" + w
    return w if re.match(r"^https?://[^\s/]+\.[^\s/]+", w) else ""


def address_flag(addr, city):
    """Mark incomplete addresses for human review instead of silently shipping them."""
    a = (addr or "").strip()
    if not a:
        return "REVIEW: no address"
    if not re.match(r"^\d", a) or city.lower() not in a.lower() or " and," in a.lower():
        return "REVIEW: address incomplete or intersection only"
    return ""


def validate_and_dedupe(leads, city, limit, words=None, niche=None, state=""):
    """Keep: has a name, is open, in the target city, has a valid phone OR website. Dedupe by phone, then name."""
    seen_phone, seen_name, seen_host, out, rejected = set(), set(), set(), [], {"no_name": 0, "closed": 0, "wrong_city": 0, "no_contact": 0, "duplicate": 0, "not_relevant": 0, "supplier_or_brand": 0, "wrong_category": 0, "out_of_area": 0}
    for l in leads:
        name = (l.get("name") or "").strip()
        if not name:
            rejected["no_name"] += 1; continue
        if l.get("_closed"):
            rejected["closed"] += 1; continue
        if l.get("_city") and l["_city"].strip().lower() != city.strip().lower():
            rejected["wrong_city"] += 1; continue
        if words:
            hay = (name + " " + (l.get("_category") or "")).lower()
            if not any(w in hay for w in words):
                rejected["not_relevant"] += 1; continue
        phone, site = norm_phone(l.get("phone")), norm_site(l.get("website"))
        if niche:
            import relevance
            rr = relevance.reject_reason(l, niche, state, re.sub(r"\D", "", phone))
            if rr:
                rejected[rr[0]] += 1; continue
        if not phone and not site:
            rejected["no_contact"] += 1; continue
        nk = re.sub(r"[^a-z0-9]", "", name.lower())
        hk = re.sub(r"^https?://(www\.)?|[/?#].*$", "", site.lower()) if site else ""
        if (phone and phone in seen_phone) or nk in seen_name or (hk and hk in seen_host):
            rejected["duplicate"] += 1; continue
        seen_phone.add(phone) if phone else None
        seen_name.add(nk)
        seen_host.add(hk) if hk else None
        flag = address_flag(l.get("address", ""), city)
        if l.get("_national"):
            flag = (flag + "; " if flag else "") + "REVIEW: national brand listing (local office)"
        attr = ""
        if l.get("_datasets") is not None:
            import overture_provider
            attr = overture_provider.attribution(l["_datasets"], l.get("source_release", ""))
        out.append({**{k: l.get(k, "") for k in CSV_COLUMNS}, "name": name, "phone": phone, "website": site,
                    "category": l.get("_category", ""), "review_flag": flag, "data_attribution": attr})
        if len(out) >= limit:
            break
    return out, rejected


def write_csv(order_id, rows):
    p = data_dir() / f"{re.sub(r'[^A-Za-z0-9_-]', '_', order_id)}.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return str(p)


# ---------------------------------------------------------------- delivery
def send_resend(to, subject, body, csv_path, idem):
    """Resend HTTPS API. Returns Resend email id on HTTP 200. Idempotency-Key prevents double sends on retry."""
    import base64
    base = os.environ.get("RESEND_API_URL", "https://api.resend.com")
    with open(csv_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    r = requests.post(base + "/emails", timeout=30, headers={
        "Authorization": "Bearer " + os.environ["RESEND_API_KEY"], "Idempotency-Key": idem,
        "User-Agent": "lyra-order-fulfillment/0.1"},
        json={"from": os.environ.get("RESEND_FROM", "Lyra Sha AI <ingrid@lyrashaai.com>"), "to": [to], "subject": subject,
              "text": body, "attachments": [{"filename": Path(csv_path).name, "content": content}]})
    if r.status_code != 200 or not r.json().get("id"):
        raise RuntimeError(f"Resend HTTP {r.status_code}: {r.text[:200]}")
    return r.json()["id"]


def send_email(to, subject, body, csv_path, idem=""):
    """Returns Message-ID after the SMTP server ACCEPTS the message. Raises DeliveryBlocked if no SMTP configured."""
    if os.environ.get("RESEND_API_KEY"):
        return send_resend(to, subject, body, csv_path, idem)
    host = os.environ.get("SMTP_HOST", "")
    if not host:
        raise DeliveryBlocked("neither RESEND_API_KEY nor SMTP_HOST configured")
    msg = EmailMessage()
    sender = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER", "")
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg["Message-ID"] = f"<{int(time.time()*1000)}.{os.getpid()}@lyrashaai.com>"
    msg.set_content(body)
    with open(csv_path, "rb") as f:
        msg.add_attachment(f.read(), maintype="text", subtype="csv", filename=Path(csv_path).name)
    port = int(os.environ.get("SMTP_PORT", "587"))
    with (smtplib.SMTP_SSL(host, port, timeout=30) if port == 465 else smtplib.SMTP(host, port, timeout=30)) as s:
        if port != 465:
            s.ehlo()
            if s.has_extn("starttls"):
                s.starttls()
            elif host not in ("127.0.0.1", "localhost"):
                raise RuntimeError("SMTP server does not offer TLS; refusing to send credentials")
        if os.environ.get("SMTP_USER"):
            s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASS", ""))
        refused = s.send_message(msg)
        if refused:
            raise RuntimeError(f"recipient refused: {refused}")
    return msg["Message-ID"]


class DeliveryBlocked(Exception):
    pass


# ---------------------------------------------------------------- pipeline
_locks = {}
_locks_guard = threading.Lock()


def process_order(order_id):
    """Idempotent: safe to call repeatedly; only one runner per order; never re-sends once EMAIL_SENT/FULFILLED."""
    with _locks_guard:
        lock = _locks.setdefault(order_id, threading.Lock())
    if not lock.acquire(blocking=False):
        return
    try:
        with db() as c:
            o = c.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
        if not o or o["status"] in ("EMAIL_SENT", "FULFILLED", "SHORTFALL"):
            return
        if o["attempts"] >= MAX_ATTEMPTS:
            return
        with db() as c:
            c.execute("UPDATE orders SET attempts=attempts+1 WHERE order_id=?", (order_id,))
        if not industry_ok(o["business_type"]):
            # paid order for an industry outside the launch menu: never fulfil, refund path handles it
            set_status(order_id, "SHORTFALL", lead_count=0,
                       last_error=f"industry '{o['business_type']}' not available at launch; NOT delivered, refund due")
            event(order_id, "INDUSTRY_NOT_ALLOWED", o["business_type"])
            return
        set_status(order_id, "PROCESSING")
        limit = min(int(o["quantity"]), int(os.environ.get("FULFILLMENT_MAX_LEADS", "25")))
        try:
            csv_path = o["csv_path"] if o["csv_path"] and os.path.exists(o["csv_path"]) else None
            if not csv_path:
                raw = find_leads(o["business_type"], o["city"], o["state"], limit * 2)
                set_status(order_id, "LEADS_FOUND", lead_count=len(raw))
                rows, rej = validate_and_dedupe(raw, o["city"], limit, niche_for(o["business_type"])[0]["words"], niche_for(o["business_type"])[1], o["state"])
                event(order_id, "VALIDATION", json.dumps({"raw": len(raw), "kept": len(rows), "rejected": rej}))
                if not rows and str(order_id).startswith("STRIPE-"):
                    set_status(order_id, "SHORTFALL", lead_count=0,
                               last_error=f"0 valid contacts of {o['quantity']} purchased for {o['business_type']} in {o['city']}, {o['state']}; NOT delivered, refund due")
                    return
                if not rows:
                    raise RuntimeError("no valid leads after validation")
                if str(order_id).startswith("STRIPE-") and len(rows) < int(o["quantity"]):
                    # paid order: never deliver or mark fulfilled with fewer contacts than purchased
                    set_status(order_id, "SHORTFALL", lead_count=len(rows),
                               last_error=f"only {len(rows)} valid contacts of {o['quantity']} purchased; NOT delivered, refund due")
                    return
                set_status(order_id, "VALIDATED", lead_count=len(rows))
                csv_path = write_csv(order_id, rows)
                set_status(order_id, "CSV_READY", csv_path=csv_path, lead_count=len(rows))
            with db() as c:
                n = c.execute("SELECT lead_count FROM orders WHERE order_id=?", (order_id,)).fetchone()[0]
            tag = "[TEST] " if o["is_test"] else ""
            attr_note = ""
            try:
                with open(csv_path, newline="", encoding="utf-8") as _f:
                    _first = next(csv.DictReader(_f), {})
                if _first.get("data_attribution"):
                    attr_note = "\n\nData source: " + _first["data_attribution"]
            except Exception:
                pass
            mid = send_email(
                o["customer_email"], f"{tag}Your {n} local {o['business_type']} business contacts in {o['city']}, {o['state']}",
                f"{tag}Order {order_id}: attached are {n} local business contacts for {o['business_type']} businesses in "
                f"{o['city']}, {o['state']}. This is publicly available business information (business name, address, and phone number and/or website where available). "
                f"It is not a list of interested customers, not verified email addresses, and not a guarantee of replies or sales. "
                f"Please verify details before outreach and follow applicable email and phone marketing laws.{attr_note}\n\n-- Lyra Sha AI",
                csv_path, idem=f"order-{order_id}")
            set_status(order_id, "EMAIL_SENT", message_id=mid)  # SMTP server accepted the message
            set_status(order_id, "FULFILLED", message_id=mid)
        except DeliveryBlocked as e:
            set_status(order_id, "DELIVERY_BLOCKED", last_error=str(e))
        except Exception as e:  # noqa
            log.exception("order %s failed", order_id)
            set_status(order_id, "FAILED", last_error=str(e)[:300])
    finally:
        lock.release()


def resume_unfinished():
    """Call at startup: re-run orders interrupted by a restart (bounded by MAX_ATTEMPTS)."""
    with db() as c:
        ids = [r[0] for r in c.execute(
            "SELECT order_id FROM orders WHERE status IN ('RECEIVED','PROCESSING','LEADS_FOUND','VALIDATED','CSV_READY','FAILED') AND attempts<?",
            (MAX_ATTEMPTS,))]
    # Stripe recovery must include its refund/alert path, including exhausted retries.
    import stripe_bridge
    stripe_bridge.resume_unfinished()
    with db() as c:
        stripe_ids = {r[0] for r in c.execute("SELECT order_id FROM stripe_orders")}
    for i in ids:
        if i not in stripe_ids:
            threading.Thread(target=process_order, args=(i,), daemon=True).start()
    return ids


# ---------------------------------------------------------------- HTTP
def secret():
    return os.environ.get("ORDER_WEBHOOK_SECRET", "")


def allowed_niches():
    """Launch menu lock (env ALLOWED_NICHES, default plumber,roofer,landscaper). Backend enforcement, independent of the website menu."""
    return {x.strip().lower() for x in os.environ.get("ALLOWED_NICHES", "plumber,roofer,landscaper").split(",") if x.strip()}


def industry_ok(btype):
    return niche_for(btype)[1] in allowed_niches()


@bp.route("/eligibility", methods=["GET"])
def eligibility():
    """Pre-payment check for a checkout-session creator: GET /eligibility?business_type=plumber"""
    b = request.args.get("business_type", "")
    return jsonify(business_type=b, eligible=industry_ok(b), allowed=sorted(allowed_niches()))


@bp.route("/webhook/order", methods=["POST"])
def order_webhook():
    if not secret():
        return jsonify(error="not configured"), 503
    raw = request.get_data()
    sig = request.headers.get("X-Lyra-Signature", "")
    if not hmac.compare_digest(sig, hmac.new(secret().encode(), raw, hashlib.sha256).hexdigest()):
        return jsonify(error="bad signature"), 401
    try:
        d = json.loads(raw)
        oid = str(d["order_id"]).strip()
        email = str(d["customer_email"]).strip().lower()
        btype, city, state = str(d["business_type"]).strip(), str(d["city"]).strip(), str(d.get("state", "")).strip()
        qty = int(d.get("quantity", 10))
        is_test = bool(d.get("test", False))
    except Exception:
        return jsonify(error="invalid order"), 400
    if not re.match(r"^[A-Za-z0-9_-]{3,64}$", oid) or not EMAIL_RE.match(email) or not btype or not city or not 1 <= qty <= 500:
        return jsonify(error="invalid order fields"), 400
    if not industry_ok(btype):
        return jsonify(error="industry not available", allowed=sorted(allowed_niches())), 422
    allowed = [e.strip().lower() for e in os.environ.get("FULFILLMENT_TEST_RECIPIENTS", "ingrid@lyrashaai.com").split(",")]
    if is_test and email not in allowed:
        return jsonify(error="test orders may only email allowlisted recipients"), 400
    qty = min(qty, int(os.environ.get("FULFILLMENT_MAX_LEADS", "25")))
    init_db()
    try:
        with db() as c:
            c.execute("INSERT INTO orders(order_id,customer_email,business_type,city,state,quantity,is_test,status,created_at,updated_at)"
                      " VALUES(?,?,?,?,?,?,?,?,?,?)", (oid, email, btype, city, state, qty, int(is_test), "RECEIVED", now(), now()))
        event(oid, "RECEIVED", "test" if is_test else "live")
    except sqlite3.IntegrityError:
        with db() as c:
            st = c.execute("SELECT status FROM orders WHERE order_id=?", (oid,)).fetchone()[0]
        event(oid, "DUPLICATE_WEBHOOK_IGNORED")
        return jsonify(order_id=oid, status=st, duplicate=True), 200
    threading.Thread(target=process_order, args=(oid,), daemon=True).start()
    return jsonify(order_id=oid, status="RECEIVED", duplicate=False), 202


@bp.route("/order-status/<oid>", methods=["GET"])
def order_status(oid):
    key = os.environ.get("ORDER_STATUS_KEY") or secret()
    if not key or not hmac.compare_digest(request.headers.get("X-Status-Key", ""), key):
        return jsonify(error="unauthorized"), 401
    init_db()
    with db() as c:
        o = c.execute("SELECT order_id,status,attempts,lead_count,message_id,last_error,created_at,updated_at FROM orders WHERE order_id=?", (oid,)).fetchone()
        ev = [dict(r) for r in c.execute("SELECT event,detail,at FROM order_events WHERE order_id=? ORDER BY id", (oid,))]
    return (jsonify({**dict(o), "events": ev}) if o else (jsonify(error="not found"), 404))


def register(app):
    """Opt-in: only active when ORDER_FULFILLMENT_ENABLED=1, so deploying this file changes nothing by default."""
    if os.environ.get("ORDER_FULFILLMENT_ENABLED", "").lower() in ("1", "true", "yes"):
        init_db()
        app.register_blueprint(bp)
        import checkout_gate
        app.register_blueprint(checkout_gate.bp2)
        resume_unfinished()
        log.info("order fulfillment webhook enabled")
