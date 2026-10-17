"""Standalone entry point for the isolated order-fulfillment test service.
Start command: python order_service.py   (does not import the live bots)."""
import os
from flask import Flask, jsonify, request, make_response
import order_fulfillment as of
import outreach_compliance as oc
import stripe_bridge

app = Flask(__name__)
os.environ.setdefault("ORDER_FULFILLMENT_ENABLED", "1")
of.register(app)
if os.environ.get("STRIPE_WEBHOOK_SECRET"):
    app.register_blueprint(stripe_bridge.bp)


PAGE = "<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'><body style='font-family:system-ui;max-width:480px;margin:60px auto;padding:0 16px'><h2>Lyra Sha AI</h2>%s</body>"


@app.route("/unsubscribe", methods=["GET", "POST"])
def unsubscribe():
    """GET shows a confirm button (so mail scanners cannot unsubscribe people);
    POST (button or RFC 8058 one-click) suppresses only if the signed token matches."""
    e = (request.values.get("e") or "").strip().lower()
    t = request.values.get("t") or ""
    if not e or not oc.SECRET or not __import__("hmac").compare_digest(t, oc.token(e)):
        return make_response(PAGE % "<p>This unsubscribe link is not valid. To stop emails, reply STOP to ingrid@lyrashaai.com.</p>", 400)
    if request.method == "POST":
        oc.suppress(e, "unsubscribe link")
        return PAGE % "<p>You have been unsubscribed and will not receive further emails from us.</p>"
    return PAGE % ("<p>Unsubscribe <b>%s</b> from Lyra Sha AI emails?</p><form method=post><input type=hidden name=e value='%s'><input type=hidden name=t value='%s'><button>Confirm unsubscribe</button></form>" % (__import__("html").escape(e), __import__("html").escape(e, True), __import__("html").escape(t, True)))


@app.route("/suppression-check")
def suppression_check():
    """Auth'd (X-Status-Key = webhook secret): returns send-gate result for one address."""
    import hmac as _h
    key = os.environ.get("ORDER_WEBHOOK_SECRET", "")
    if not key or not _h.compare_digest(request.headers.get("X-Status-Key", ""), key):
        return jsonify(error="unauthorized"), 401
    e = (request.args.get("e") or "").strip().lower()
    return jsonify(email=e, suppressed=oc.is_suppressed(e), preflight=oc.preflight(e, "body"))


ALLOWED_DEFAULT = "ingrid@lyrashaai.com"


@app.route("/outreach/send", methods=["POST"])
def outreach_send():
    """Authenticated (X-Status-Key). Body JSON: to, subject, body (may contain {UNSUB_URL}), dry_run.
    Only recipients listed in OUTREACH_ALLOWED_RECIPIENTS (default: founder only) can be sent to."""
    import hmac as _h, requests as _rq
    key = os.environ.get("ORDER_WEBHOOK_SECRET", "")
    if not key or not _h.compare_digest(request.headers.get("X-Status-Key", ""), key):
        return jsonify(error="unauthorized"), 401
    j = request.get_json(force=True, silent=True) or {}
    to = (j.get("to") or "").strip().lower(); subject = j.get("subject") or ""
    allowed = [a.strip().lower() for a in os.environ.get("OUTREACH_ALLOWED_RECIPIENTS", ALLOWED_DEFAULT).split(",") if a.strip()]
    if to not in allowed:
        return jsonify(error="recipient not in OUTREACH_ALLOWED_RECIPIENTS"), 403
    link = oc.unsub_url(to)
    text = (j.get("body") or "").replace("{UNSUB_URL}", link)
    blockers = oc.preflight(to, text)
    if "{UNSUB_URL}" in (j.get("body") or "") and not link:
        blockers.append("no unsubscribe link")
    if blockers:
        return jsonify(sent=False, blockers=blockers), 409
    payload = {"from": oc.FROM, "to": [to], "reply_to": oc.REPLY_TO, "subject": subject, "text": text, "headers": oc.headers(to)}
    if j.get("dry_run", True):
        return jsonify(sent=False, dry_run=True, payload=payload)
    r = _rq.post("https://api.resend.com/emails", json=payload, timeout=30,
                 headers={"Authorization": "Bearer " + os.environ["RESEND_API_KEY"], "Idempotency-Key": j.get("idem") or ""})
    rid = (r.json() or {}).get("id") if r.ok else None
    if rid:
        with oc._db() as c:
            c.execute("INSERT INTO sent VALUES(?,?,?,datetime('now'))", (to, j.get("campaign", "test"), rid))
    return jsonify(sent=bool(rid), status=r.status_code, resend_id=rid, error=None if rid else r.text[:200])


@app.route("/health")
def health():
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
