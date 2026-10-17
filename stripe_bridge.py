"""Stripe -> order fulfillment bridge (isolated test service only).
POST /stripe/webhook  with Stripe-Signature (t=..,v1=HMAC_SHA256(whsec, "t.payload")).
Fulfills ONLY checkout.session.completed / async_payment_succeeded with payment_status=paid.
Order fields come from the Checkout Session metadata: business_type, city, state, quantity.
Safety defaults: test-mode events only (STRIPE_ACCEPT_LIVE!=1); delivery goes to the founder test
recipient, not the customer (STRIPE_DELIVER_TO_CUSTOMER!=1). Dedup by Stripe event id AND session id."""
import hashlib, hmac, json, os, re, sqlite3, threading, time
from flask import Blueprint, jsonify, request
import order_fulfillment as of

bp = Blueprint("stripe_bridge", __name__)
TOLERANCE = 300
OK_TYPES = ("checkout.session.completed", "checkout.session.async_payment_succeeded")


def _flag(name):
    return os.environ.get(name, "").lower() in ("1", "true", "yes")


def verify(raw, header, secret, now=None):
    try:
        parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
        t = int(parts["t"])
    except Exception:
        return False
    sigs = [p.split("=", 1)[1] for p in header.split(",") if p.startswith("v1=")]
    if abs((now or time.time()) - t) > TOLERANCE:
        return False
    exp = hmac.new(secret.encode(), f"{t}.".encode() + raw, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(exp, s) for s in sigs)


def _seen(event_id):
    with of.db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS stripe_events(event_id TEXT PRIMARY KEY, at TEXT)")
        try:
            c.execute("INSERT INTO stripe_events VALUES(?,?)", (event_id, of.now()))
            return False
        except sqlite3.IntegrityError:
            return True


@bp.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        return jsonify(error="not configured"), 503
    raw = request.get_data()
    if not verify(raw, request.headers.get("Stripe-Signature", ""), secret):
        return jsonify(error="bad signature"), 400
    try:
        ev = json.loads(raw); eid = ev["id"]; typ = ev["type"]
        s = ev["data"]["object"]
    except Exception:
        return jsonify(error="invalid event"), 400
    of.init_db()
    if bool(ev.get("livemode")) and not _flag("STRIPE_ACCEPT_LIVE"):
        return jsonify(ignored="live-mode events disabled"), 200
    if typ not in OK_TYPES:
        return jsonify(ignored=typ), 200
    if s.get("payment_status") != "paid":
        return jsonify(ignored="not paid"), 200
    if _seen(eid):
        return jsonify(duplicate=True, event=eid), 200
    m = s.get("metadata") or {}
    sid = str(s.get("id", ""))
    oid = "STRIPE-" + re.sub(r"[^A-Za-z0-9_-]", "", sid)[-40:]
    try:
        btype, city = str(m["business_type"]).strip(), str(m["city"]).strip()
        state = str(m.get("state", "")).strip(); qty = int(m.get("quantity", 10))
        cust = str((s.get("customer_details") or {}).get("email") or s.get("customer_email") or "").strip().lower()
        paid = int(s.get("amount_total") or 0)
    except Exception:
        return jsonify(error="missing order metadata"), 400
    min_c = int(os.environ.get("LEADLIST_MIN_CENTS_PER_LEAD", "0"))
    if not btype or not city or not 1 <= qty <= 500 or not of.EMAIL_RE.match(cust) or not re.match(r"^[A-Za-z0-9_-]{3,64}$", oid):
        return jsonify(error="invalid order fields"), 400
    if paid < qty * min_c:
        of.event(oid, "UNDERPAID", f"paid={paid} need>={qty*min_c}")
        return jsonify(error="amount below price for quantity"), 400
    to_customer = _flag("STRIPE_DELIVER_TO_CUSTOMER")
    email = cust if to_customer else os.environ.get("FULFILLMENT_TEST_RECIPIENTS", "ingrid@lyrashaai.com").split(",")[0].strip().lower()
    qty = min(qty, int(os.environ.get("FULFILLMENT_MAX_LEADS", "25")))
    try:
        with of.db() as c:
            c.execute("INSERT INTO orders(order_id,customer_email,business_type,city,state,quantity,is_test,status,created_at,updated_at)"
                      " VALUES(?,?,?,?,?,?,?,?,?,?)", (oid, email, btype, city, state, qty, 0 if to_customer else 1, "RECEIVED", of.now(), of.now()))
        of.event(oid, "RECEIVED", f"stripe event={eid} livemode={bool(ev.get('livemode'))} paid={paid} deliver_to_customer={to_customer}")
    except sqlite3.IntegrityError:
        of.event(oid, "DUPLICATE_SESSION_IGNORED", eid)
        return jsonify(order_id=oid, duplicate=True), 200
    threading.Thread(target=of.process_order, args=(oid,), daemon=True).start()
    return jsonify(order_id=oid, status="RECEIVED", duplicate=False), 200
