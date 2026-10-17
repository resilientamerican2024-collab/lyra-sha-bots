"""Standalone entry point for the isolated order-fulfillment test service.
Start command: python order_service.py   (does not import the live bots)."""
import os
from flask import Flask, jsonify, request, make_response
import order_fulfillment as of
import outreach_compliance as oc

app = Flask(__name__)
os.environ.setdefault("ORDER_FULFILLMENT_ENABLED", "1")
of.register(app)


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


@app.route("/health")
def health():
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
