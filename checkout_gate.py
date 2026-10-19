"""Pre-payment eligibility gate; live mode requires the complete explicit launch configuration.
POST /checkout/session  {product, business_type, city, state, quantity[, email][, price_cents]}
Validates BEFORE any Stripe session exists: approved product, allowed industry, launch location, quantity, price, and that
enough qualified contacts exist right now. If STRIPE_CHECKOUT_KEY (a TEST-mode key) is set it then creates the Checkout Session;
otherwise it returns the validated session parameters (dry run). Live keys require explicit launch gates. The post-payment guards, idempotency and
auto-refund in order_fulfillment/stripe_bridge remain as backup. No fulfillment logic lives here."""
import os, re, time, threading
from flask import Blueprint, request, jsonify

bp2 = Blueprint("checkout_gate", __name__)
PRODUCT = "10-local-business-contacts"
ALLOWED_KEYS = {"product", "business_type", "city", "state", "quantity", "email", "price_cents", "locale"}
_cache, _lk = {}, threading.Lock()


def price_cents():
    # Founder-approved offer; configuration must not silently change the price.
    return 2900


def qualified_count(niche, city, state):
    """Count contacts that would pass the full validation right now (cached 10 min). Never calls a paid provider."""
    import order_fulfillment as of
    if os.environ.get("LEADS_PROVIDER", "osm").lower() != "overture":
        return 0
    k = (niche, city.lower(), state.upper())
    with _lk:
        hit = _cache.get(k)
        if hit and time.time() - hit[0] < 600:
            return hit[1]
    raw = of.find_leads(niche, city, state, 200)
    rows, _ = of.validate_and_dedupe(raw, city, 200, of.niche_for(niche)[0]["words"], niche, state)
    with _lk:
        _cache[k] = (time.time(), len(rows))
    return len(rows)


def check(d):
    """Return (ok, http_status, payload)."""
    import order_fulfillment as of
    if not isinstance(d, dict):
        return False, 400, {"error": "invalid request"}
    extra = set(d) - ALLOWED_KEYS
    if extra:
        return False, 400, {"error": "unexpected fields", "fields": sorted(extra)}
    if d.get("product") != PRODUCT:
        return False, 422, {"error": "unapproved product"}
    bt = d.get("business_type")
    if not isinstance(bt, str) or not of.industry_ok(bt):
        return False, 422, {"error": "industry not available", "allowed": sorted(of.allowed_niches())}
    niche = of.niche_for(bt)[1]
    city, state = d.get("city"), d.get("state")
    if not (isinstance(city, str) and isinstance(state, str) and city.strip().lower() == "cheyenne"
            and state.strip().upper() in ("WY", "WYOMING")):
        return False, 422, {"error": "location not available", "available": "Cheyenne, WY"}
    q = d.get("quantity")
    if isinstance(q, bool) or q != 10 or not isinstance(q, int):
        return False, 422, {"error": "quantity must be exactly 10"}
    if "price_cents" in d and d["price_cents"] != price_cents():
        return False, 422, {"error": "price mismatch"}
    locale = d.get("locale", "auto")
    if locale not in ("auto", "en", "es", "es-419"):
        return False, 422, {"error": "unsupported locale"}
    email = d.get("email")
    if email is not None and not (isinstance(email, str) and re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) and len(email) < 255):
        return False, 422, {"error": "invalid email"}
    n = qualified_count(niche, "Cheyenne", "WY")
    if n < 10:
        return False, 409, {"error": "not enough qualified contacts right now", "qualified": n, "needed": 10}
    params = {"mode": "payment", "line_items[0][price_data][currency]": "usd",
              "line_items[0][price_data][unit_amount]": str(price_cents()),
              "line_items[0][price_data][product_data][name]": ("10 Local Business Contacts" if os.environ.get("STRIPE_CHECKOUT_LIVE") == "1" else "10 Local Business Contacts (TEST)"),
              "line_items[0][quantity]": "1", "metadata[business_type]": niche, "metadata[city]": "Cheyenne",
              "metadata[state]": "WY", "metadata[product]": PRODUCT, "locale": locale, "metadata[quantity]": "10", "metadata[prechecked]": "1",
              "success_url": os.environ.get("CHECKOUT_SUCCESS_URL", "https://lyrashaai.com/"),
              "cancel_url": os.environ.get("CHECKOUT_CANCEL_URL", "https://lyrashaai.com/")}
    if email:
        params["customer_email"] = email
    return True, 200, {"eligible": True, "qualified": n, "price_cents": price_cents(), "business_type": niche, "stripe_params": params}


@bp2.route("/checkout/session", methods=["POST"])
def checkout_session():
    d = request.get_json(silent=True)
    ok, code, body = check(d)
    if not ok:
        return jsonify(body), code
    key = os.environ.get("STRIPE_CHECKOUT_KEY", "")
    if not key:
        return jsonify({**body, "created": False, "note": "dry run: STRIPE_CHECKOUT_KEY not configured"}), 200
    live = key.startswith(("rk_live_", "sk_live_"))
    test = key.startswith(("rk_test_", "sk_test_"))
    if not (live or test):
        return jsonify(error="invalid checkout key configuration"), 503
    if live and os.environ.get("STRIPE_CHECKOUT_LIVE") != "1":
        return jsonify(error="live checkout disabled"), 403
    if os.environ.get("STRIPE_CHECKOUT_LIVE") == "1":
        from launch_config import live_blockers
        if live_blockers():
            return jsonify(error="live checkout not ready"), 503
    import requests
    try:
        r = requests.post("https://api.stripe.com/v1/checkout/sessions", data=body["stripe_params"],
                          headers={"Authorization": f"Bearer {key}"}, timeout=20)
    except requests.RequestException:
        return jsonify(error="checkout temporarily unavailable"), 502
    if r.status_code != 200:
        return jsonify(error="stripe error", status=r.status_code), 502
    s = r.json()
    return jsonify(created=True, session_id=s.get("id"), url=s.get("url"), qualified=body["qualified"]), 200
