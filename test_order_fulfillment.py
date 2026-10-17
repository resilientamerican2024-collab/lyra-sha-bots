"""E2E test: signed webhook -> leads -> validation -> CSV -> SMTP -> status; replay must not re-send.
Run: python test_order_fulfillment.py   (uses a local SMTP sink unless SMTP_HOST already set;
set LEADS_PROVIDER=osm for live free lead data, or FAKE_LEADS=1 for offline logic test)."""
import hashlib, hmac, json, os, sys, tempfile, time
from email import message_from_bytes
os.environ.setdefault("ORDER_WEBHOOK_SECRET", "test-secret-" + str(os.getpid()))
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
os.environ["ORDER_FULFILLMENT_ENABLED"] = "1"
sink = []
if not os.environ.get("SMTP_HOST"):
    from aiosmtpd.controller import Controller
    class H:
        async def handle_DATA(self, server, session, envelope):
            sink.append((envelope.rcpt_tos, envelope.content)); return "250 OK"
    ctl = Controller(H(), hostname="127.0.0.1", port=8026); ctl.start()
    os.environ.update(SMTP_HOST="127.0.0.1", SMTP_PORT="8026", SMTP_FROM="ingrid@lyrashaai.com")
import order_fulfillment as of
if os.environ.get("FAKE_LEADS"):
    of.find_leads = lambda *a: [
        {"name": "Acme Plumbing", "phone": "307-555-0101", "website": "acme.example", "_city": "Cheyenne"},
        {"name": "ACME  Plumbing", "phone": "(307) 555-0101", "_city": "Cheyenne"},
        {"name": "", "phone": "307-555-0102", "_city": "Cheyenne"},
        {"name": "Nowhere Pipes", "_city": "Cheyenne"},
        {"name": "Denver Rooter", "phone": "303-555-0103", "_city": "Denver"},
        {"name": "Old Co", "phone": "307-555-0104", "_city": "Cheyenne", "_closed": True},
        {"name": "Capital City Drains", "phone": "+1 307 555 0105", "_city": "Cheyenne"}]
from flask import Flask
app = Flask(__name__); of.register(app); c = app.test_client()
S = os.environ["ORDER_WEBHOOK_SECRET"]
def post(body, sig=None):
    raw = json.dumps(body).encode()
    return c.post("/webhook/order", data=raw, headers={"X-Lyra-Signature": sig or hmac.new(S.encode(), raw, hashlib.sha256).hexdigest(), "Content-Type": "application/json"})
order = {"order_id": "TEST-CHEY-PLUMB-001", "customer_email": "ingrid@lyrashaai.com", "business_type": "Plumber",
         "city": "Cheyenne", "state": "WY", "quantity": 10, "test": True}
res = {}
res["bad_signature_rejected"] = post(order, "0"*64).status_code == 401
res["outside_recipient_rejected"] = post({**order, "order_id": "TEST-X-002", "customer_email": "someone@else.com"}).status_code == 400
r1 = post(order); res["accepted_202"] = r1.status_code == 202
for _ in range(60):
    st = c.get("/order-status/" + order["order_id"], headers={"X-Status-Key": S}).get_json()
    if st["status"] in ("FULFILLED", "FAILED", "DELIVERY_BLOCKED"): break
    time.sleep(2)
print(json.dumps(st, indent=1))
res["final_status_FULFILLED"] = st["status"] == "FULFILLED"
n_before = len(sink)
r2 = post(order); time.sleep(3)
res["replay_returns_duplicate"] = r2.status_code == 200 and r2.get_json()["duplicate"] is True
res["replay_sent_no_second_email"] = len(sink) == n_before
if sink:
    m = message_from_bytes(sink[0][1]); att = [p for p in m.walk() if p.get_filename()]
    res["email_has_csv_attachment"] = bool(att)
    print("TO:", sink[0][0], "SUBJECT:", m["Subject"])
    print(att[0].get_payload(decode=True).decode() if att else "")
for k, v in res.items(): print(("PASS " if v else "FAIL ") + k)
sys.exit(0 if all(res.values()) else 1)
